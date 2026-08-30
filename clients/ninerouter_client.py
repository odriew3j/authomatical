import logging

import requests

from config import Config

logger = logging.getLogger(__name__)


class NineRouterClient:
    """Talks to a local NineRouter instance (an OpenAI-compatible gateway
    that can fan a request out to several backend models).

    Two failure modes matter here and are handled explicitly:
    - HTTP/connection/timeout errors -> retried.
    - HTTP 200 with a response that isn't actually usable (no `choices`,
      `message.content` missing/empty, or a JSON body that got cut off
      mid-string because the backend hit its own max_tokens) -> also
      retried, since a 200 status code alone does NOT mean we got a
      usable completion.

    `model` defaults to Config.NINEROUTER_MODEL rather than a router-picks
    -whatever model like "code-9router-combo": that combo can land on a
    slow reasoning backend (e.g. deepseek-r1) that spends most of its
    token budget on a <think> block and then gets truncated before
    producing any real JSON. Pinning a known-good model makes behavior
    predictable; callers can still override per-call if needed.
    """

    BASE = "http://localhost:20128/v1"

    def __init__(self, api_key=None, verify_ssl=True, model=None):
        self.api_key = api_key or Config.NINEROUTER_API_KEY
        self.verify_ssl = verify_ssl
        self.model = model or Config.NINEROUTER_MODEL

        if not self.api_key:
            raise ValueError("NINEROUTER_API_KEY is missing in config!")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat(self, messages, model=None, max_tokens=2000, temperature=0.7):
        url = f"{self.BASE}/chat/completions"
        selected_model = model or self.model

        payload = {
            "model": selected_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        last_response = None

        for attempt in range(1, Config.MAX_RETRIES + 1):
            logger.info(
                "9Router request: model=%s attempt=%s/%s",
                selected_model, attempt, Config.MAX_RETRIES,
            )

            try:
                response = requests.post(
                    url, json=payload, headers=self.headers,
                    timeout=Config.TIMEOUT, verify=self.verify_ssl,
                )
                last_response = response

                if not response.ok:
                    logger.warning(
                        "9Router HTTP error: status=%s body=%s",
                        response.status_code, response.text[:2000],
                    )
                    continue

                try:
                    data = response.json()
                except ValueError:
                    # Usually means the backend's output got cut off
                    # mid-string (e.g. hit max_tokens) and the JSON body
                    # itself is malformed — not recoverable by re-parsing,
                    # only by asking again.
                    logger.warning(
                        "9Router returned unparsable JSON body "
                        "(likely truncated mid-generation): %s",
                        response.text[:2000],
                    )
                    continue

                if not isinstance(data, dict) or not data.get("choices"):
                    logger.warning("9Router response has no choices: %s", str(data)[:2000])
                    continue

                choice = data["choices"][0]
                message = choice.get("message") or {}
                content = message.get("content")
                finish_reason = choice.get("finish_reason")

                logger.info(
                    "9Router response: model=%s finish_reason=%s",
                    data.get("model"), finish_reason,
                )

                if not content or not str(content).strip():
                    # Reasoning-only response (content empty, only
                    # `reasoning` populated) or genuinely empty output.
                    logger.warning(
                        "9Router returned no usable content. "
                        "finish_reason=%s reasoning=%s",
                        finish_reason, str(message.get("reasoning"))[:1000],
                    )
                    continue

                if finish_reason == "length":
                    # Content exists but may be truncated mid-JSON. We
                    # still hand it back — the caller (ProductBuilder /
                    # ArticleBuilder) knows how to try to salvage/parse
                    # it and logs finish_reason for diagnosis — but this
                    # is worth flagging loudly here too.
                    logger.warning(
                        "9Router output was truncated (finish_reason=length). "
                        "Consider raising max_tokens if this repeats."
                    )

                return data

            except requests.Timeout as exc:
                logger.warning(
                    "9Router timeout attempt=%s/%s: %s",
                    attempt, Config.MAX_RETRIES, exc,
                )
            except requests.RequestException as exc:
                logger.warning(
                    "9Router connection error attempt=%s/%s: %s",
                    attempt, Config.MAX_RETRIES, exc,
                )

        if last_response is not None:
            raise RuntimeError(
                f"9Router API error {last_response.status_code}: {last_response.text[:2000]}"
            )
        raise RuntimeError("Could not connect to 9Router.")

    def generate_image(self, prompt, model="dall-e-3", size="1792x1024"):
        url = f"{self.BASE}/images/generate"
        payload = {"model": model, "prompt": prompt, "size": size}
        last_response = None

        for attempt in range(1, Config.MAX_RETRIES + 1):
            logger.info("9Router image request: model=%s attempt=%s/%s", model, attempt, Config.MAX_RETRIES)
            try:
                response = requests.post(
                    url, json=payload, headers=self.headers,
                    timeout=Config.TIMEOUT, verify=self.verify_ssl,
                )
                last_response = response
                if response.ok:
                    try:
                        return response.json()
                    except ValueError:
                        logger.error("9Router image endpoint returned invalid JSON: %s", response.text[:2000])
                        continue
                logger.warning("9Router image HTTP error %s: %s", response.status_code, response.text[:1000])
            except requests.Timeout as exc:
                logger.warning("9Router image timeout: %s", exc)
            except requests.RequestException as exc:
                logger.warning("9Router image connection error: %s", exc)

        if last_response is not None:
            raise RuntimeError(
                f"9Router image API error {last_response.status_code}: {last_response.text[:2000]}"
            )
        raise RuntimeError("Could not connect to 9Router.")

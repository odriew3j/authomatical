import logging

import requests

from config import Config

logger = logging.getLogger(__name__)


class OpenRouterClient:
    """Client for OpenRouter's OpenAI-compatible Chat Completions API."""

    BASE = "https://openrouter.ai/api/v1"

    def __init__(self, api_key=None, verify_ssl=True, model=None):
        self.api_key = api_key or Config.OPENROUTER_API_KEY
        self.verify_ssl = verify_ssl
        self.model = model or Config.OPENROUTER_MODEL

        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY is missing in config!")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat(
        self,
        messages,
        model=None,
        max_tokens=2000,
        temperature=0.7,
    ):
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
                "OpenRouter request: model=%s attempt=%s/%s",
                selected_model,
                attempt,
                Config.MAX_RETRIES,
            )

            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=self.headers,
                    timeout=Config.TIMEOUT,
                    verify=self.verify_ssl,
                )

                last_response = response

                if not response.ok:
                    logger.warning(
                        "OpenRouter HTTP error: status=%s body=%s",
                        response.status_code,
                        response.text[:2000],
                    )
                    continue

                try:
                    data = response.json()
                except ValueError:
                    logger.warning(
                        "OpenRouter returned invalid JSON: %s",
                        response.text[:2000],
                    )
                    continue

                if not isinstance(data, dict):
                    logger.warning(
                        "OpenRouter response is not a JSON object: %s",
                        str(data)[:2000],
                    )
                    continue

                if not data.get("choices"):
                    logger.warning(
                        "OpenRouter response has no choices: %s",
                        str(data)[:2000],
                    )
                    continue

                choice = data["choices"][0]

                message = choice.get("message") or {}
                content = message.get("content")
                finish_reason = choice.get("finish_reason")

                logger.info(
                    "OpenRouter response: model=%s finish_reason=%s",
                    data.get("model"),
                    finish_reason,
                )

                if not content or not str(content).strip():

                    logger.warning(
                        "OpenRouter returned no usable content. "
                        "finish_reason=%s reasoning=%s",
                        finish_reason,
                        str(message.get("reasoning", ""))[:1000],
                    )

                    continue

                if finish_reason == "length":
                    logger.warning(
                        "OpenRouter output was truncated "
                        "(finish_reason=length)."
                    )

                return data

            except requests.Timeout as exc:

                logger.warning(
                    "OpenRouter timeout attempt=%s/%s: %s",
                    attempt,
                    Config.MAX_RETRIES,
                    exc,
                )

            except requests.RequestException as exc:

                logger.warning(
                    "OpenRouter connection error attempt=%s/%s: %s",
                    attempt,
                    Config.MAX_RETRIES,
                    exc,
                )

        if last_response is not None:
            raise RuntimeError(
                f"OpenRouter API error "
                f"{last_response.status_code}: "
                f"{last_response.text[:2000]}"
            )

        raise RuntimeError("Could not connect to OpenRouter.")

    def generate_image(
        self,
        prompt,
        model="dall-e-3",
        size="1792x1024",
    ):
        url = f"{self.BASE}/images/generate"

        payload = {
            "model": model,
            "prompt": prompt,
            "size": size,
        }

        last_response = None

        for attempt in range(1, Config.MAX_RETRIES + 1):

            logger.info(
                "OpenRouter image request: model=%s attempt=%s/%s",
                model,
                attempt,
                Config.MAX_RETRIES,
            )

            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=self.headers,
                    timeout=Config.TIMEOUT,
                    verify=self.verify_ssl,
                )

                last_response = response

                if response.ok:
                    try:
                        return response.json()
                    except ValueError:
                        logger.warning(
                            "OpenRouter image endpoint returned invalid JSON: %s",
                            response.text[:2000],
                        )
                        continue

                logger.warning(
                    "OpenRouter image HTTP error %s: %s",
                    response.status_code,
                    response.text[:1000],
                )

            except requests.Timeout as exc:
                logger.warning("OpenRouter image timeout: %s", exc)

            except requests.RequestException as exc:
                logger.warning(
                    "OpenRouter image connection error: %s",
                    exc,
                )

        if last_response is not None:
            raise RuntimeError(
                f"OpenRouter image API error "
                f"{last_response.status_code}: "
                f"{last_response.text[:2000]}"
            )

        raise RuntimeError("Could not connect to OpenRouter.")
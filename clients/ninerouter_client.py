# clients/ninerouter_client.py

import logging
import requests

from config import Config


logger = logging.getLogger(__name__)


class NineRouterClient:
    BASE = "http://localhost:20128/v1"

    def __init__(
        self,
        api_key=None,
        verify_ssl=True,
        model="code-9router-combo",
    ):
        self.api_key = api_key or Config.NINEROUTER_API_KEY
        self.verify_ssl = verify_ssl
        self.model = model

        if not self.api_key:
            raise ValueError("NINEROUTER_API_KEY is missing in config!")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat(
        self,
        messages,
        model=None,
        max_tokens=2000,
        temperature=None,
    ):
        url = f"{self.BASE}/chat/completions"

        selected_model = model or self.model

        payload = {
            "model": selected_model,
            "messages": messages,
            "max_tokens": max_tokens,
        }

        if temperature is not None:
            payload["temperature"] = temperature

        last_response = None

        for attempt in range(1, Config.MAX_RETRIES + 1):

            try:
                logger.info(
                    "9Router request: model=%s attempt=%s/%s",
                    selected_model,
                    attempt,
                    Config.MAX_RETRIES,
                )

                response = requests.post(
                    url,
                    json=payload,
                    headers=self.headers,
                    timeout=Config.TIMEOUT,
                    verify=self.verify_ssl,
                )

                last_response = response

                # -------------------------------------------------
                # HTTP error
                # -------------------------------------------------
                if not response.ok:
                    logger.warning(
                        "9Router HTTP error: status=%s body=%s",
                        response.status_code,
                        response.text[:2000],
                    )
                    continue

                # -------------------------------------------------
                # JSON parsing
                # -------------------------------------------------
                try:
                    data = response.json()
                except ValueError:
                    logger.warning(
                        "9Router returned invalid JSON: %s",
                        response.text[:2000],
                    )
                    continue

                # -------------------------------------------------
                # Validate choices
                # -------------------------------------------------
                choices = data.get("choices")

                if not choices:
                    logger.warning(
                        "9Router response has no choices: %s",
                        data,
                    )
                    continue

                choice = choices[0]

                finish_reason = choice.get("finish_reason")

                message = choice.get("message") or {}

                content = message.get("content")

                reasoning = message.get("reasoning")

                # -------------------------------------------------
                # IMPORTANT:
                # Some models may return only reasoning and no
                # assistant content.
                # -------------------------------------------------
                if not content or not str(content).strip():

                    logger.warning(
                        "9Router returned empty content. "
                        "finish_reason=%s model=%s reasoning=%s",
                        finish_reason,
                        data.get("model"),
                        str(reasoning)[:1000],
                    )

                    continue

                # -------------------------------------------------
                # Successful response
                # -------------------------------------------------
                logger.info(
                    "9Router success: model=%s finish_reason=%s",
                    data.get("model"),
                    finish_reason,
                )

                return data

            except requests.RequestException as exc:
                logger.warning(
                    "9Router connection error attempt=%s/%s: %s",
                    attempt,
                    Config.MAX_RETRIES,
                    exc,
                )

                continue

        # ---------------------------------------------------------
        # All attempts failed
        # ---------------------------------------------------------
        if last_response is not None:

            raise RuntimeError(
                f"9Router API error {last_response.status_code}: "
                f"{last_response.text[:2000]}"
            )

        raise RuntimeError(
            "Could not connect to 9Router."
        )

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
                    return response.json()

                logger.warning(
                    "9Router image API error: status=%s body=%s",
                    response.status_code,
                    response.text[:2000],
                )

            except requests.RequestException as exc:
                logger.warning(
                    "9Router image connection error: %s",
                    exc,
                )

        if last_response is not None:
            raise RuntimeError(
                f"9Router image API error "
                f"{last_response.status_code}: "
                f"{last_response.text[:2000]}"
            )

        raise RuntimeError(
            "Could not connect to 9Router."
        )
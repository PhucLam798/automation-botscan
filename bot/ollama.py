"""Ollama chay local (mac dinh http://127.0.0.1:11434), chi dung thu vien chuan.

API: POST /api/chat voi "format" = JSON schema -> model tra ve JSON dung khuon.
Khong can key, khong mat phi, khong gui noi dung bai ra ngoai may.
"""
import json
import logging
import os
import re
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

DEFAULT_HOST = "http://127.0.0.1:11434"
TIMEOUT = 300  # CPU cham: lan dau nap model co the mat 1-2 phut


class OllamaError(RuntimeError):
    def __init__(self, message, skip=False):
        super().__init__(message)
        self.skip = skip  # loi rieng bai nay (JSON hong): bo bai, doc bai khac


def host():
    return (os.environ.get("OLLAMA_HOST") or DEFAULT_HOST).rstrip("/")


def _request(path, body=None, timeout=TIMEOUT):
    request = urllib.request.Request(
        host() + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            message = json.loads(error.read().decode("utf-8", "replace")).get("error", "")
        except (ValueError, AttributeError):
            message = ""
        raise OllamaError(f"Ollama loi {error.code}: {message or error.reason}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise OllamaError(f"Khong ket noi duoc Ollama o {host()} ({type(error).__name__}). "
                          "Bat Ollama: sudo systemctl start ollama") from None
    except ValueError:
        raise OllamaError("Ollama tra ve du lieu hong") from None


def installed_models():
    return [m.get("name", "") for m in _request("/api/tags", timeout=10).get("models") or []]


def has_model(model):
    names = installed_models()
    return model in names or (":" not in model and f"{model}:latest" in names)


def pull(model):
    """Tai model, in tien do ra man hinh."""
    request = urllib.request.Request(host() + "/api/pull", data=json.dumps({"model": model}).encode(),
                                     headers={"Content-Type": "application/json"})
    last = ""
    try:
        with urllib.request.urlopen(request, timeout=3600) as response:
            for line in response:
                data = json.loads(line or b"{}")
                if data.get("error"):
                    raise OllamaError(f"Khong tai duoc {model}: {data['error']}")
                status, total = data.get("status", ""), data.get("total")
                text = f"{status} {data.get('completed', 0) * 100 // total}%" if total else status
                if text != last:
                    print(f"\r  {text:<60}", end="", flush=True)
                    last = text
    except (urllib.error.URLError, OSError) as error:
        raise OllamaError(f"Khong tai duoc {model}: {error}") from None
    print()


def chat_json(model, system, prompt, schema, options=None):
    """Mot luot hoi dap, tra ve dict theo schema."""
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "format": schema,
        "stream": False,
        "think": False,          # tat che do suy nghi: nhanh hon nhieu tren CPU
        "keep_alive": "15m",
        "options": {"temperature": 0.6, "num_ctx": 4096, "num_predict": 400, **(options or {})},
    }
    try:
        try:
            data = _request("/api/chat", body)
        except OllamaError as error:
            if "think" not in str(error):
                raise
            body.pop("think")  # model khong ho tro tham so think
            data = _request("/api/chat", body)
    except OllamaError as error:
        if "not found" in str(error):
            raise OllamaError(f"Chua tai model {model}: chay python3 main.py --setup") from None
        raise
    text =str((data.get("message") or {}).get("content") or "").strip()
    log.debug("Ollama %s (%.1f giay): %s", model, (data.get("total_duration") or 0) / 1e9, text)
    if text.startswith("```"):
        text = re.sub(r"^```\w*\s*|\s*```$", "", text)
    try:
        result = json.loads(text)
    except ValueError:
        result = None
    if not isinstance(result, dict):
        raise OllamaError("Model tra ve JSON hong", skip=True)
    return result

import requests

from . import config, storage


def send_robot_markdown(title: str, text: str, ticket_id: int | None = None) -> tuple[bool, str]:
    webhook = config.DINGTALK_WEBHOOK
    if not webhook:
        storage.log_dingtalk_notify(ticket_id, None, "skipped", "webhook 未配置")
        return False, "webhook 未配置"
    payload = {"msgtype": "markdown", "markdown": {"title": title, "text": text}}
    try:
        response = requests.post(webhook, json=payload, timeout=10)
        data = response.json()
        ok = data.get("errcode") == 0
        storage.log_dingtalk_notify(
            ticket_id,
            webhook[:80],
            "success" if ok else "failed",
            str(data)[:400],
        )
        return ok, str(data)
    except Exception as exc:
        storage.log_dingtalk_notify(ticket_id, webhook[:80], "failed", str(exc)[:200])
        return False, str(exc)


def send_robot_text(
    text: str,
    at_mobiles: list[str] | None = None,
    ticket_id: int | None = None,
) -> tuple[bool, str]:
    webhook = config.DINGTALK_WEBHOOK
    if not webhook:
        storage.log_dingtalk_notify(ticket_id, None, "skipped", "webhook 未配置")
        return False, "webhook 未配置"
    payload = {"msgtype": "text", "text": {"content": text}}
    if at_mobiles:
        payload["at"] = {"atMobiles": at_mobiles, "isAtAll": False}
    try:
        response = requests.post(webhook, json=payload, timeout=10)
        data = response.json()
        ok = data.get("errcode") == 0
        storage.log_dingtalk_notify(
            ticket_id,
            webhook[:80],
            "success" if ok else "failed",
            str(data)[:400],
        )
        return ok, str(data)
    except Exception as exc:
        storage.log_dingtalk_notify(ticket_id, webhook[:80], "failed", str(exc)[:200])
        return False, str(exc)

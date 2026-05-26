import json
import urllib.request
import logging

logger = logging.getLogger(__name__)


def _post_json(url: str, payload: dict) -> bool:
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status < 300
    except Exception as e:
        logger.error("Webhook POST failed %s: %s", url, e)
        return False


def send_teams(url: str, device_name: str, ip: str, alert_type: str, timestamp: str) -> bool:
    is_down = alert_type == "down"
    color   = "FF0000" if is_down else "00AA00"
    title   = "🔴 障害検知 (DOWN)" if is_down else "🟢 復旧 (UP)"

    payload = {
        "@type":    "MessageCard",
        "@context": "https://schema.org/extensions",
        "themeColor": color,
        "summary": f"{title}: {device_name}",
        "sections": [{
            "activityTitle":    title,
            "activitySubtitle": f"{device_name}  ({ip})",
            "facts": [
                {"name": "デバイス名", "value": device_name},
                {"name": "IPアドレス", "value": ip},
                {"name": "検知時刻",   "value": timestamp},
            ],
            "markdown": True,
        }],
    }
    ok = _post_json(url, payload)
    logger.info("Teams notify %s → %s", title, "OK" if ok else "FAIL")
    return ok


def send_slack(url: str, device_name: str, ip: str, alert_type: str, timestamp: str) -> bool:
    is_down = alert_type == "down"
    color   = "#f85149" if is_down else "#3fb950"
    title   = "🔴 障害検知 (DOWN)" if is_down else "🟢 復旧 (UP)"

    payload = {
        "attachments": [{
            "color": color,
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": title},
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*デバイス名*\n{device_name}"},
                        {"type": "mrkdwn", "text": f"*IPアドレス*\n`{ip}`"},
                        {"type": "mrkdwn", "text": f"*検知時刻*\n{timestamp}"},
                    ],
                },
            ],
        }]
    }
    ok = _post_json(url, payload)
    logger.info("Slack notify %s → %s", title, "OK" if ok else "FAIL")
    return ok


def notify_threshold(device_name: str, ip: str, metric: str, alert_kind: str,
                     value: float, threshold: float, timestamp: str, settings: dict,
                     if_name: str = "") -> None:
    """RTT または帯域幅の閾値アラート通知を送信する。"""
    is_high = alert_kind.endswith("high")
    notify_down = str(settings.get("notify_on_down",     "1")) == "1"
    notify_rec  = str(settings.get("notify_on_recovery", "1")) == "1"
    if is_high and not notify_down:
        return
    if not is_high and not notify_rec:
        return

    if metric == "rtt":
        icon   = "🟡" if is_high else "🟢"
        title  = f"{'⚠ RTT 超過' if is_high else '✅ RTT 回復'}"
        detail = f"RTT: {value:.1f}ms（閾値: {threshold:.0f}ms）"
    else:
        icon   = "🟡" if is_high else "🟢"
        title  = f"{'⚠ 帯域超過' if is_high else '✅ 帯域回復'}"
        iface_info = f"  インターフェース: {if_name}" if if_name else ""
        detail = f"使用率: {value:.1f}%（閾値: {threshold:.0f}%）{iface_info}"

    teams_url = settings.get("teams_webhook_url", "").strip()
    slack_url = settings.get("slack_webhook_url", "").strip()

    color = "FFA500" if is_high else "00AA00"
    if teams_url:
        payload = {
            "@type":    "MessageCard",
            "@context": "https://schema.org/extensions",
            "themeColor": color,
            "summary": f"{title}: {device_name}",
            "sections": [{
                "activityTitle":    f"{icon} {title}",
                "activitySubtitle": f"{device_name}  ({ip})",
                "facts": [
                    {"name": "デバイス名", "value": device_name},
                    {"name": "IPアドレス", "value": ip},
                    {"name": "詳細",       "value": detail},
                    {"name": "検知時刻",   "value": timestamp},
                ],
                "markdown": True,
            }],
        }
        ok = _post_json(teams_url, payload)
        logger.info("Teams threshold notify %s → %s", title, "OK" if ok else "FAIL")

    if slack_url:
        sl_color = "#FFA500" if is_high else "#3fb950"
        payload = {
            "attachments": [{
                "color": sl_color,
                "blocks": [
                    {"type": "header",
                     "text": {"type": "plain_text", "text": f"{icon} {title}"}},
                    {"type": "section",
                     "fields": [
                         {"type": "mrkdwn", "text": f"*デバイス名*\n{device_name}"},
                         {"type": "mrkdwn", "text": f"*IPアドレス*\n`{ip}`"},
                         {"type": "mrkdwn", "text": f"*詳細*\n{detail}"},
                         {"type": "mrkdwn", "text": f"*検知時刻*\n{timestamp}"},
                     ]},
                ],
            }]
        }
        ok = _post_json(slack_url, payload)
        logger.info("Slack threshold notify %s → %s", title, "OK" if ok else "FAIL")


def notify(device_name: str, ip: str, alert_type: str, timestamp: str, settings: dict):
    """Send notifications to all configured destinations."""
    is_down     = alert_type == "down"
    notify_down = str(settings.get("notify_on_down",     "1")) == "1"
    notify_rec  = str(settings.get("notify_on_recovery", "1")) == "1"

    if is_down and not notify_down:
        return
    if not is_down and not notify_rec:
        return

    teams_url = settings.get("teams_webhook_url", "").strip()
    slack_url = settings.get("slack_webhook_url", "").strip()

    if teams_url:
        send_teams(teams_url, device_name, ip, alert_type, timestamp)
    if slack_url:
        send_slack(slack_url, device_name, ip, alert_type, timestamp)

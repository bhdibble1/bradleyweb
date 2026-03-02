# SS/emailer.py
import os
import requests

RESEND_ENDPOINT = "https://api.resend.com/emails"

def _build_from(from_email: str | None, from_name: str | None) -> str | None:
    """
    Returns a valid RFC5322 From field:
      - "Name <email@domain>"  (preferred)
      - "email@domain"
    If the caller already passed "Name <email@domain>", just return it.
    """
    if not from_email:
        return None
    s = from_email.strip()
    # If already "Name <email@domain>", keep as-is
    if "<" in s and ">" in s:
        return s
    # Otherwise, add display name if provided
    return f"{(from_name or '').strip()} <{s}>" if from_name else s

def send_email(
    to,
    subject: str,
    html: str,
    from_email: str | None = None,
    from_name: str | None = None,
    reply_to: str | list[str] | None = None,
    attachments: list[dict] | None = None,
) -> bool:
    """
    Send an HTML email via Resend using only `requests`.
    ENV required:
      - RESEND_API_KEY
      - FROM_EMAIL  (fallback, must be on your verified domain)
      - FROM_NAME   (optional)
    Notes:
      - `to` can be a string or list of strings
      - `reply_to` can be a string or list
      - `attachments` optional list of {"filename": str, "content": base64_str}
    """
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        print("⚠️ RESEND_API_KEY not set; skipping email.")
        return False

    # Prefer explicit args, fallback to env
    from_email = from_email or os.environ.get("FROM_EMAIL")
    from_name = from_name or os.environ.get("FROM_NAME", "Bradley Dibble")

    if not from_email:
        print("⚠️ FROM_EMAIL not set and no from_email argument given; skipping email.")
        return False

    # Guard against using Gmail/etc. (Resend requires your verified domain)
    if from_email.lower().endswith("@gmail.com"):
        print("⚠️ FROM_EMAIL is a Gmail address. Use your verified domain instead.")
        return False

    from_field = _build_from(from_email, from_name)
    if not from_field:
        print("⚠️ Could not build a valid From header; skipping email.")
        return False

    # Normalize to list
    to_list = to if isinstance(to, list) else [to]
    reply_to_val = reply_to
    if isinstance(reply_to, str):
        reply_to_val = [reply_to]

    payload = {
        "from": from_field,
        "to": to_list,
        "subject": subject,
        "html": html,
    }
    if reply_to_val:
        payload["reply_to"] = reply_to_val
    if attachments:
        payload["attachments"] = attachments

    try:
        resp = requests.post(
            RESEND_ENDPOINT,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )
        print("📨 Resend response:", resp.status_code, resp.text[:500])

        if resp.status_code == 403 and "domain is not verified" in resp.text.lower():
            print("🔎 Your sender domain isn’t verified in Resend. Verify DNS first.")
        if resp.status_code == 422 and "Invalid `from` field" in resp.text:
            print("🔎 Fix FROM format: use `orders@send.yourdomain.com` or `Name <orders@send.yourdomain.com>`.")

        return resp.ok
    except requests.RequestException as e:
        print("❌ Resend request failed:", e)
        return False

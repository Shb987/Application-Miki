from datetime import datetime, timezone, timedelta
from typing import Optional, Union
import pytz

# Indian Standard Time (IST) Timezone
IST = pytz.timezone("Asia/Kolkata")
IST_OFFSET = timezone(timedelta(hours=5, minutes=30))


def get_ist_now() -> datetime:
    """Return the current time in Indian Standard Time (IST)."""
    return datetime.now(IST)


def to_ist(dt_val: Union[datetime, str, None]) -> Optional[datetime]:
    """
    Convert any datetime object or ISO datetime string to an aware datetime in IST.
    If the input is naive (no timezone), it is assumed to be UTC (standard MongoDB/server storage).
    """
    if not dt_val:
        return None

    if isinstance(dt_val, str):
        try:
            clean = dt_val.strip()
            if clean.endswith("Z"):
                clean = clean[:-1] + "+00:00"
            dt = datetime.fromisoformat(clean)
        except Exception:
            try:
                import dateutil.parser
                dt = dateutil.parser.parse(clean)
            except Exception:
                return None
    elif isinstance(dt_val, datetime):
        dt = dt_val
    else:
        return None

    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)

    return dt.astimezone(IST)


def to_ist_iso(dt_val: Union[datetime, str, None]) -> str:
    """
    Convert any datetime object or ISO datetime string to an Indian Standard Time ISO string (+05:30).
    Falls back gracefully if the input cannot be parsed.
    """
    dt_ist = to_ist(dt_val)
    if dt_ist is not None:
        return dt_ist.isoformat()
    return str(dt_val) if dt_val is not None else ""


def to_ist_display(dt_val: Union[datetime, str, None], fmt: str = "%d-%m-%Y %I:%M %p") -> str:
    """
    Format a datetime or ISO string into a human-readable IST string, e.g. '05-11-2026 05:30 PM'.
    """
    dt_ist = to_ist(dt_val)
    if dt_ist is not None:
        return dt_ist.strftime(fmt)
    return str(dt_val) if dt_val is not None else ""

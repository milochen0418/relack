"""Message times, formatted in the browser: its own time zone and language.

Messages store Unix time; messages imported from before that only have an
"HH:MM" string, shown as is (the fallback).
"""

import reflex as rx
from reflex.vars.function import FunctionStringVar

_TIME = FunctionStringVar.create(
    "((t, fallback) => t ? new Date(t * 1000).toLocaleTimeString([],"
    " {hour: '2-digit', minute: '2-digit', hour12: false}) : (fallback || ''))"
)
_DATETIME = FunctionStringVar.create(
    "((t, fallback) => t ? new Date(t * 1000).toLocaleString([], {year: 'numeric', month: 'short',"
    " day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false}) : (fallback || ''))"
)
# "Today" / "Yesterday" / "Tuesday, October 28" (with the year when not this year);
# "" when `prev` is on the same day, so a divider shows only where the day changes.
_DAY = FunctionStringVar.create(
    """((t, prev) => {
      if (!t) return '';
      const d = new Date(t * 1000);
      if (prev && new Date(prev * 1000).toDateString() === d.toDateString()) return '';
      const now = new Date();
      const days = Math.round((new Date(now.toDateString()) - new Date(d.toDateString())) / 86400000);
      if (days === 0 || days === 1) {
        const s = new Intl.RelativeTimeFormat([], {numeric: 'auto'}).format(-days, 'day');
        return s.charAt(0).toUpperCase() + s.slice(1);
      }
      const opts = {weekday: 'long', month: 'long', day: 'numeric'};
      if (d.getFullYear() !== now.getFullYear()) opts.year = 'numeric';
      return d.toLocaleDateString([], opts);
    })"""
)


def local_time(ts, fallback="") -> rx.Var:
    """HH:MM of a Unix time."""
    return _TIME.call(ts, fallback).to(str)


def local_datetime(ts, fallback="") -> rx.Var:
    """Date and time of a Unix time (tooltips, tables)."""
    return _DATETIME.call(ts, fallback).to(str)


def day_label(ts, prev) -> rx.Var:
    """Day divider text for a message after one sent at `prev` ("" on the same day)."""
    return _DAY.call(ts, prev).to(str)

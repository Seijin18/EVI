"""Windmill client shim — backward-compat re-exporter.

All HTTP logic now lives in agent/integrations/windmill.py.
External callers that import post_windmill() directly continue to work.
"""

from integrations.windmill import _windmill_post as _post


def post_windmill(
    env_var: str,
    payload: dict,
    default_url: str,
    timeout: int = 30,
    wait_result: bool = False,
) -> str:
    return _post(env_var, payload, default_url, timeout=timeout, wait_result=wait_result)

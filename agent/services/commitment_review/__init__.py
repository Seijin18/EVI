from services.commitment_review.handler import try_direct_review


def maybe_notify_new_pending(*args, **kwargs):
    from services.commitment_review.deliver import maybe_notify_new_pending as _fn

    return _fn(*args, **kwargs)


__all__ = ["maybe_notify_new_pending", "try_direct_review"]

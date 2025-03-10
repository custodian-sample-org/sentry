"""
Outbox messages are how we propagate state changes between Silos

Region & Control Silos can publish outbox messages which are propagated asynchronously to
the 'other' silo. This means that outbox messages created on a Region Silo are pushed to
the Control Silo, and outbox messages created on the Control Silo are pushed to relevant Region Silos.

Messages are considered relevant to a Region Silo if there is a chance that a region has
a record that relies on the outbox message. Often this boils down to relations to organizations
or users. However, SentryApps and ApiApplications are special.

### Message Types & Directionality

Within the outbox functionality there are two outbox models:

- `RegionOutbox` is for messages made in a Region that need to be delivered to Control Silo
- `ControlOutbox` is for messages made in Control Silo that need to be propagated to Region Silos.

### Saving outbox messages

When ORM models have changes made that need to be propagated to the 'other' silo(s)
you must use a database transaction to perform the side-effect and outbox messages.
Doing both in a single database transactions ensures that outbox messages are only
persisted alongside the change that as persisted.

ex.

```python
# Within Organization.delete()
with transaction.atomic():
    Organization.outbox_for_update(self.id).save()
    return super().delete(**kwargs)
```

### Outbox message delivery

Outbox messages are delivered periodically (each minute) by the `sentry.tasks.enqueue_outbox_jobs`.
This task runs in both Control and Region Silos and delivers messages to their destination Silo.

Should delivery fail for any reason, it will remain in the outbox until it can be successfully
delivered. Outbox messages will be delivered by cross-region RPC calls.

### Processing outbox messages

When an outbox message is received via RPC, it is processed by a signal handler. Signal handlers can
be found in sentry.receivers.outbox.control and sentry.receivers.outbox.region. Outbox receivers are
fired according to the message type. For example when a ControlOutbox message is received and processed
on Region Silos the relevant receiver in `receivers.outbox.control` will be called.
Similarily, when a RegionOutbox message is received and processed on Control Silo the relevant
receiver in `receivers.outbox.region` will be called.

See https://www.notion.so/sentry/Async-cross-region-updates-outbox-9330293c8d2f4bd497361a505fd355d3
"""
from __future__ import annotations

from typing import Any, Protocol, Type, TypeVar

from sentry.services.hybrid_cloud.tombstone import RpcTombstone, tombstone_service


class ModelLike(Protocol):
    objects: Any


T = TypeVar("T", bound=ModelLike)


def maybe_process_tombstone(model: Type[T], object_identifier: int) -> T | None:
    if instance := model.objects.filter(id=object_identifier).last():
        return instance

    tombstone_service.record_remote_tombstone(
        RpcTombstone(table_name=model._meta.db_table, identifier=object_identifier)
    )
    return None

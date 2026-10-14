from .models import AuditEvent


def audit(workspace, user, action, target, access_change=False):
    if access_change:
        workspace.access_epoch += 1
        workspace.save(update_fields=["access_epoch", "updated_at"])
    AuditEvent.objects.create(workspace=workspace, actor=user, action=action, target_id=target.pk)

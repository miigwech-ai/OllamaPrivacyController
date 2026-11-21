"""Model cleanup module - isolated from general cleanup for safety.
Model cleanup requires plan binding and shared-blob protection before enablement.
"""
import threading
from checks.saved_models import SavedModelsCheck
from checks.context import ScanContext

MODEL_CLEANUP_LOCK = threading.Lock()


def plan_model_cleanup():
    """Generate a cleanup plan for saved models only.
    Uses isolated lock separate from general cleanup.
    """
    if not MODEL_CLEANUP_LOCK.acquire(False):
        return {'error': 'Model cleanup operation already in progress.', 'status': 409}
    try:
        context = ScanContext.current()
        checker = SavedModelsCheck()
        plan = checker.plan(context)
        return {
            'plan': plan.to_dict(),
            'status': 200
        }
    finally:
        MODEL_CLEANUP_LOCK.release()


def execute_model_cleanup(confirmed=False):
    """Execute model cleanup with confirmation.
    DISABLED until plan binding and shared-blob protection are implemented.
    """
    if not confirmed:
        return {'error': 'Confirmation required for cleanup.', 'status': 400}

    # DISABLED: Model cleanup requires plan binding and shared-blob protection
    return {
        'error': 'Model cleanup is disabled until plan binding and shared-blob protection are implemented.',
        'status': 503
    }


def verify_model_cleanup():
    """Verify model cleanup by re-inspecting the models directory."""
    context = ScanContext.current()
    checker = SavedModelsCheck()
    verification = checker.inspect(context)
    return verification.to_dict()

from .cli_history import CliHistoryCheck
from .desktop_database import DesktopDatabaseCheck
from .logs import LogsCheck
from .saved_models import SavedModelsCheck
CHECKS=(CliHistoryCheck(),DesktopDatabaseCheck(),LogsCheck(),SavedModelsCheck())

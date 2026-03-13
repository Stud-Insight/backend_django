"""TER API controllers."""

from .balancing import TERBalancingController
from .dashboard import TERDashboardController
from .deliverables import TERDeliverablesController
from .grading import TERGradingController, TERPeerReviewController
from .periods import TERPeriodController
from .rankings import TERRankingController
from .student import TERStudentController
from .subjects import TERSubjectController

__all__ = [
    "TERPeriodController",
    "TERSubjectController",
    "TERRankingController",
    "TERBalancingController",
    "TERDashboardController",
    "TERDeliverablesController",
    "TERGradingController",
    "TERPeerReviewController",
    "TERStudentController",
]

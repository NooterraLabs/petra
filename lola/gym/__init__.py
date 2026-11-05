"""Training environment and baseline agent. Untrusted; the reward comes from the kernel."""
from __future__ import annotations

from .agent import AgentStats, BaselineAgent, run_episodes
from .env import LolaEnv, Submission
from .tasks import GENERATORS, Task

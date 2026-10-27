"""Shared test setup. No test here calls Gemini or the network."""
import os
from unittest import mock

import agents


class OfflineAgentsMixin:
    """Run the agents with the rule-based classifier and hashed embeddings."""

    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {"FAKE_LLM": "1", "FAKE_EMBEDDINGS": "1"})
        env.start()
        self.addCleanup(env.stop)
        llm = mock.patch.object(agents, "FAKE_LLM", True)
        llm.start()
        self.addCleanup(llm.stop)
        agents.get_embeddings.cache_clear()
        agents.get_rules_store.cache_clear()
        self.addCleanup(agents.get_embeddings.cache_clear)
        self.addCleanup(agents.get_rules_store.cache_clear)

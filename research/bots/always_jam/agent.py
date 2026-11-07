"""Test opponent (not a submission): all-in whenever it can raise, else call; default select."""

import poker_agent_sdk
from poker_agent_sdk import Action


class Agent(poker_agent_sdk.Agent):
    def act(self, state, memory):
        if state.phase != "betting":
            first = state.legal_actions[0]
            return Action(first.kind, first.min_amount), memory
        r = state.can("raise")
        if r:
            return Action.raise_to(r.max_amount), memory
        if state.can("call"):
            return Action.call(), memory
        return Action.check(), memory

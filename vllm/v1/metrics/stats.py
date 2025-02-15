# SPDX-License-Identifier: Apache-2.0

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from vllm.outputs import RequestOutput
    from vllm.v1.engine import EngineCoreOutput, FinishReason


@dataclass
class PrefixCacheStats:
    """Stores prefix cache hit statistics."""
    # Whether reset_prefix_cache was invoked.
    reset: bool = False
    # The number of requests in this update.
    requests: int = 0
    # The number of queries in these requests. Note that "queries" here
    # means the number of blocks that were queried from the cache.
    queries: int = 0
    # The number of hits in these requests.
    hits: int = 0


@dataclass
class SchedulerStats:
    """Stats associated with the scheduler."""

    num_running_reqs: int = 0
    num_waiting_reqs: int = 0

    gpu_cache_usage: float = 0.0

    prefix_cache_stats: PrefixCacheStats = field(
        default_factory=PrefixCacheStats)


@dataclass
class RequestStateStats:
    """Stats that need to be tracked across delta updates."""

    num_generation_tokens: int = 0
    last_token_time: float = 0.0


@dataclass
class FinishedRequestStats:
    """Stats associated with a finished request."""

    finish_reason: "FinishReason"
    num_prompt_tokens: int = 0
    num_generation_tokens: int = 0


class IterationStats:
    """Stats associated with a single set of EngineCoreOutputs."""

    def __init__(self, log_stats: bool):
        self.log_stats = log_stats
        self.num_generation_tokens = 0
        self.num_prompt_tokens = 0
        self.finished_requests: List[FinishedRequestStats] = []
        self.time_to_first_tokens_iter: List[float] = []
        self.time_per_output_tokens_iter: List[float] = []

    def update_from_output(self, output: "EngineCoreOutput",
                           is_prefilling: bool, prompt_len: int,
                           request_state_stats: RequestStateStats):
        if not self.log_stats:
            return

        num_new_generation_tokens = len(output.new_token_ids)
        now = time.time()
        last_token_latency = now - request_state_stats.last_token_time

        self.num_generation_tokens += num_new_generation_tokens
        if is_prefilling:
            # TODO(andy): we used to assert that num_new_generation_tokens
            # > 0 with an invariant that EngineCore does not stream outputs
            # for partially completed prefills (scheduler.update_from_output
            # makes EngineCoreOutput iff num_computed_tokens == num_tokens).
            # When prompt logprobs are enabled, we currently stream out the
            # partially completed prompt.
            # This will be reverted in a follow up PR and we should re-enable
            # this assertion / invariant.
            if num_new_generation_tokens > 0:
                self.num_prompt_tokens += prompt_len
                self.time_to_first_tokens_iter.append(last_token_latency)
        else:
            self.time_per_output_tokens_iter.append(last_token_latency)

        request_state_stats.num_generation_tokens += num_new_generation_tokens
        request_state_stats.last_token_time = now

    def update_from_finished_request(self, finish_reason: "FinishReason",
                                     request_output: "RequestOutput",
                                     request_state_stats: RequestStateStats):
        self.finished_requests.append(
            FinishedRequestStats(finish_reason,
                                 len(request_output.prompt_token_ids),
                                 request_state_stats.num_generation_tokens))

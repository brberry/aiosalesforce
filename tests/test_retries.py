from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aiosalesforce.exceptions import SalesforceError
from aiosalesforce.retries import ExceptionRule, ResponseRule, RetryPolicy
from httpx import Response


class TestRules:
    @pytest.mark.parametrize("sync", [True, False], ids=["sync", "async"])
    @pytest.mark.parametrize(
        "decision",
        [True, False],
        ids=["should_retry", "should_not_retry"],
    )
    async def test_response_rule(self, sync: bool, decision: bool):
        func = MagicMock() if sync else AsyncMock()
        func.return_value = decision
        rule = ResponseRule(func)
        response = Response(500)
        assert await rule.should_retry(response) == decision
        func.assert_called_with(response)

    @pytest.mark.parametrize("sync", [True, False], ids=["sync", "async"])
    @pytest.mark.parametrize(
        "decision",
        [True, False],
        ids=["should_retry", "should_not_retry"],
    )
    async def test_exception_rule(self, sync: bool, decision: bool):
        func = MagicMock() if sync else AsyncMock()
        func.return_value = decision
        rule = ExceptionRule(ValueError, func)

        # Matching exception
        exception_1 = ValueError("Test")
        assert await rule.should_retry(exception_1) == decision
        func.assert_called_with(exception_1)

        # Different exception (always False, doesn't call the function)
        exception_2 = TypeError("Test")
        assert not await rule.should_retry(exception_2)  # type: ignore
        func.assert_called_once()

    async def test_exception_rule_base_not_allowed(self):
        with pytest.raises(
            ValueError,
            match="Retrying built-in Exception is not allowed.",
        ):
            ExceptionRule(Exception)

    async def test_exception_rule_salesforce_not_allowed(self):
        with pytest.raises(
            ValueError,
            match="aiosalesforce exceptions cannot be retried.+",
        ):
            ExceptionRule(SalesforceError)


class TestRetryPolicy:
    async def test_sleep(self):
        policy = RetryPolicy()
        new_sleep = AsyncMock()
        with patch("asyncio.sleep", new_sleep):
            new_sleep.assert_not_awaited()
            await policy.sleep(1)
            new_sleep.assert_awaited_once()

    async def test_without_rules(self):
        policy = RetryPolicy()
        context = policy.create_context()

        assert context.retry_count["total"] == 0
        assert not await context.should_retry(Response(500))
        assert context.retry_count["total"] == 0

    @pytest.mark.parametrize("sync", [True, False], ids=["sync", "async"])
    @pytest.mark.parametrize(
        "decision",
        [True, False],
        ids=["should_retry", "should_not_retry"],
    )
    async def test_with_response_rule(self, sync: bool, decision: bool):
        rule_callback = MagicMock() if sync else AsyncMock()
        rule_callback.return_value = decision
        rule = ResponseRule(rule_callback, 3)
        policy = RetryPolicy([rule], max_retries=10)
        context = policy.create_context()

        assert context.retry_count["total"] == 0
        assert await context.should_retry(Response(500)) == decision
        assert context.retry_count["total"] == int(decision)

        # Exhaust rule retries (policy retries are not exhausted)
        if decision:
            for _ in range(2):
                assert await context.should_retry(Response(500)) == decision
            assert context.retry_count["total"] == 3
            assert not await context.should_retry(Response(500))

    @pytest.mark.parametrize("sync", [True, False], ids=["sync", "async"])
    @pytest.mark.parametrize(
        "decision",
        [True, False],
        ids=["should_retry", "should_not_retry"],
    )
    async def test_with_exception_rule(self, sync: bool, decision: bool):
        rule_callback = MagicMock() if sync else AsyncMock()
        rule_callback.return_value = decision
        rule = ExceptionRule(ValueError, rule_callback, 3)
        policy = RetryPolicy([], [rule], max_retries=10)
        context = policy.create_context()

        assert context.retry_count["total"] == 0
        assert await context.should_retry(ValueError("Test")) == decision
        assert context.retry_count["total"] == int(decision)

        # Exhaust rule retries (policy retries are not exhausted)
        if decision:
            for _ in range(2):
                assert await context.should_retry(ValueError("Test")) == decision
            assert context.retry_count["total"] == 3
            assert not await context.should_retry(ValueError("Test"))

    async def test_policy_retry_exhaustion(self):
        rule_callback = MagicMock()
        rule_callback.return_value = True
        rule = ResponseRule(rule_callback, 10)
        policy = RetryPolicy([rule], max_retries=3)
        context = policy.create_context()

        assert context.retry_count["total"] == 0
        for _ in range(3):
            assert await context.should_retry(Response(500))
        assert context.retry_count["total"] == 3
        assert not await context.should_retry(Response(500))
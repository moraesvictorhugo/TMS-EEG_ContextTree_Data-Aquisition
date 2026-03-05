"""
Tests for the context-tree sequence generator.

These tests don't need any hardware — they verify the mathematical
properties of the sequence generation algorithm.

Run with:  uv run pytest
"""
from tms_eeg.sequence import generate_sequence, _zero_branch, _next_symbol


class TestZeroBranch:
    """Tests for the probabilistic branch after symbol 0."""

    def test_returns_1_or_2(self):
        """_zero_branch should only return 1 or 2."""
        results = {_zero_branch() for _ in range(200)}
        assert results == {1, 2}


class TestNextSymbol:
    """Tests for the deterministic context-tree rules."""

    def test_after_2_gives_1(self):
        assert _next_symbol([0, 2]) == 1
        assert _next_symbol([1, 2]) == 1
        assert _next_symbol([2, 2]) == 1

    def test_after_0_1_gives_1(self):
        assert _next_symbol([0, 1]) == 1

    def test_after_1_1_gives_0(self):
        assert _next_symbol([1, 1]) == 0

    def test_after_2_1_gives_0(self):
        assert _next_symbol([2, 1]) == 0

    def test_after_0_gives_1_or_2(self):
        """After symbol 0, the next must be 1 or 2 (probabilistic)."""
        results = {_next_symbol([1, 0]) for _ in range(200)}
        assert results == {1, 2}


class TestGenerateSequence:
    """Tests for the full sequence generation."""

    def test_length(self):
        """Sequence length must match the requested number of stimuli."""
        seq = generate_sequence(100)
        assert len(seq) == 100

    def test_length_small(self):
        seq = generate_sequence(5)
        assert len(seq) == 5

    def test_only_valid_symbols(self):
        """Every element in the sequence must be 0, 1, or 2."""
        seq = generate_sequence(500)
        assert all(s in (0, 1, 2) for s in seq)

    def test_tree_rules_hold(self):
        """Verify that every transition in the sequence follows the context-tree rules."""
        seq = generate_sequence(1000)

        for i in range(2, len(seq)):
            prev = seq[i - 1]
            prev2 = seq[i - 2]
            current = seq[i]

            # After 2 → must be 1
            if prev == 2:
                assert current == 1, f"Position {i}: after 2 expected 1, got {current}"

            # After (0, 1) → must be 1
            if prev2 == 0 and prev == 1:
                assert current == 1, f"Position {i}: after (0,1) expected 1, got {current}"

            # After (1, 1) → must be 0
            if prev2 == 1 and prev == 1:
                assert current == 0, f"Position {i}: after (1,1) expected 0, got {current}"

            # After (2, 1) → must be 0
            if prev2 == 2 and prev == 1:
                assert current == 0, f"Position {i}: after (2,1) expected 0, got {current}"

            # After 0 → must be 1 or 2
            if prev == 0:
                assert current in (1, 2), f"Position {i}: after 0 expected 1 or 2, got {current}"

    def test_distribution_is_reasonable(self):
        """Check that all three symbols appear in a large sequence
        (they should, given the branching probabilities).
        """
        seq = generate_sequence(1000)
        counts = {0: 0, 1: 0, 2: 0}
        for s in seq:
            counts[s] += 1

        # All symbols must appear at least once in 1000 trials
        for symbol in (0, 1, 2):
            assert counts[symbol] > 0, f"Symbol {symbol} never appeared in 1000 trials"

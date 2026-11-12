"""
Tests for sequence generation and export.

These tests don't need any hardware — they verify the mathematical
properties of the sequence generation algorithm.

Run with:  uv run pytest
"""
import pytest

from tms_eeg.sequence import (
    generate_sequence,
    generate_pseudo_random_sequence,
    export_sequence,
    _zero_branch,
    _next_symbol,
)


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


class TestGeneratePseudoRandomSequence:
    """Verify structural guarantees without relying on random frequencies."""

    @pytest.mark.parametrize("n_stimuli", [0, 1, 2, 400, 10000])
    def test_length_symbols_and_no_consecutive_repetitions(self, n_stimuli):
        seq = generate_pseudo_random_sequence(n_stimuli)
        assert len(seq) == n_stimuli
        assert all(symbol in (0, 1, 2) for symbol in seq)
        assert all(previous != current for previous, current in zip(seq, seq[1:]))

    def test_two_symbols_alternate_without_modifying_alphabet(self):
        alphabet = [0, 2]
        seq = generate_pseudo_random_sequence(100, alphabet)
        assert set(seq) == {0, 2}
        assert seq[::2] == [seq[0]] * 50
        assert seq[1::2] == [seq[1]] * 50
        assert alphabet == [0, 2]

    def test_single_symbol_for_one_trial(self):
        assert generate_pseudo_random_sequence(1, [2]) == [2]

    def test_single_symbol_for_zero_trials(self):
        assert generate_pseudo_random_sequence(0, [2]) == []

    def test_choice_receives_only_allowed_candidates(self, monkeypatch):
        candidates_seen = []

        def choose_first(candidates):
            candidates_seen.append(list(candidates))
            return candidates[0]

        monkeypatch.setattr("tms_eeg.sequence.random.choice", choose_first)
        assert generate_pseudo_random_sequence(4) == [0, 1, 0, 1]
        assert candidates_seen == [[0, 1, 2], [1, 2], [0, 2], [1, 2]]

    @pytest.mark.parametrize(
        "n_stimuli, alphabet, message",
        [
            (-1, [0, 1, 2], "non-negative"),
            (0, [], "empty"),
            (1, [], "empty"),
            (10, [0, 0, 1], "distinct"),
            (2, [0], "At least two"),
        ],
    )
    def test_invalid_inputs(self, n_stimuli, alphabet, message):
        with pytest.raises(ValueError, match=message):
            generate_pseudo_random_sequence(n_stimuli, alphabet)


class TestExportSequence:
    @pytest.mark.parametrize(
        "algorithm, prefix",
        [("context tree", "tree_sequence"), ("pseudo-random", "pseudo_random_sequence")],
    )
    def test_filename_and_content(self, tmp_path, algorithm, prefix):
        export_sequence([0, 2, 1], 3, "V00", tmp_path, algorithm=algorithm)
        output = tmp_path / f"{prefix}_3_trials_V00.txt"
        assert output.read_text() == "0\n2\n1\n"
        assert list(tmp_path.iterdir()) == [output]

    def test_legacy_call_retains_tree_filename(self, tmp_path):
        export_sequence([0, 1], 2, "V01", tmp_path)
        assert (tmp_path / "tree_sequence_2_trials_V01.txt").read_text() == "0\n1\n"

    def test_invalid_algorithm_does_not_write_file(self, tmp_path):
        with pytest.raises(ValueError, match="Unknown sequence algorithm"):
            export_sequence([0, 1], 2, "V00", tmp_path, algorithm="invalid")
        assert list(tmp_path.iterdir()) == []

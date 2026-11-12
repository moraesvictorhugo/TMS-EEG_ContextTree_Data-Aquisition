"""
Context-tree and pseudo-random sequence generation for the TMS-EEG experiment.

The sequence follows a deterministic tree with probabilistic branching:
  - After symbol 2 → always 1
  - After symbol 0 → 30% chance of 1, 70% chance of 2
  - After (0, 1) → 1
  - After (1, 1) → 0
  - After (2, 1) → 0
"""
import random

import numpy as np
import pandas as pd


def _zero_branch():
    """Return the next symbol after a 0, based on probabilistic branching.

    Returns
    -------
    int
        1 with 30% probability, 2 with 70% probability.
    """
    return 1 if random.randrange(100) <= 30 else 2


def _next_symbol(prev_two):
    """Return the next symbol given the two most recent symbols.

    Parameters
    ----------
    prev_two : list[int]
        The last two symbols in the sequence, e.g. [1, 0].

    Returns
    -------
    int
        The next symbol (0, 1, or 2).

    Raises
    ------
    ValueError
        If prev_two does not match any known context-tree rule.
    """
    second_last, last = prev_two

    if last == 2:
        return 1
    if last == 0:
        return _zero_branch()
    # last == 1
    if second_last == 0:
        return 1
    if second_last in (1, 2):
        return 0

    raise ValueError(
        f"Unexpected context ({second_last}, {last}) — "
        "this indicates a bug in the context-tree rules."
    )


def generate_sequence(n_stimuli, alphabet=None):
    """Generate a full context-tree stimulus sequence.

    Parameters
    ----------
    n_stimuli : int
        Total number of stimuli to generate.
    alphabet : list[int], optional
        Possible first symbols. Defaults to [0, 1, 2].

    Returns
    -------
    list[int]
        The generated sequence of length *n_stimuli*.
    """
    if alphabet is None:
        alphabet = [0, 1, 2]

    sequence = [random.choice(alphabet)]

    # Second element: special initialization
    if sequence[0] == 0:
        sequence.append(_zero_branch())
    else:
        # both 1 and 2 lead to appending 1
        sequence.append(1)

    # Remaining elements follow the context-tree rules
    for _ in range(n_stimuli - 2):
        sequence.append(_next_symbol(sequence[-2:]))

    return sequence


def generate_pseudo_random_sequence(n_stimuli, alphabet=None):
    """Generate a sequence without consecutive repetitions.

    Each symbol is chosen uniformly from the alphabet, excluding the previous
    symbol. Counts are not required to be balanced across stimulus types.

    Parameters
    ----------
    n_stimuli : int
        Non-negative number of stimuli to generate.
    alphabet : list[int], optional
        Distinct stimulus symbols. Defaults to [0, 1, 2]. At least two
        symbols are needed when requesting more than one stimulus.

    Returns
    -------
    list[int]
        The generated sequence of length *n_stimuli*.

    Raises
    ------
    ValueError
        If the count is negative or the alphabet cannot satisfy the rules.
    """
    if alphabet is None:
        alphabet = [0, 1, 2]

    if n_stimuli < 0:
        raise ValueError("n_stimuli must be non-negative.")
    if not alphabet:
        raise ValueError("alphabet must not be empty.")
    if len(set(alphabet)) != len(alphabet):
        raise ValueError("alphabet must contain distinct symbols.")
    if n_stimuli > 1 and len(alphabet) < 2:
        raise ValueError("At least two symbols are needed to avoid repetitions.")
    if n_stimuli == 0:
        return []

    sequence = [random.choice(alphabet)]
    for _ in range(n_stimuli - 1):
        candidates = [symbol for symbol in alphabet if symbol != sequence[-1]]
        sequence.append(random.choice(candidates))

    return sequence


def print_sequence_stats(sequence):
    """Print the distribution of symbols in the sequence.

    Parameters
    ----------
    sequence : list[int]
        The generated sequence.
    """
    counts = pd.Series(sequence).value_counts().sort_index()
    print("Generated sequence:", sequence)
    print("Count per type:\n", counts)


def export_sequence(
    sequence, n_stimuli, volunteer_code, output_dir=".", algorithm="context tree"
):
    """Save the sequence to a text file.

    Parameters
    ----------
    sequence : list[int]
        The generated sequence.
    n_stimuli : int
        Number of stimuli (used in filename).
    volunteer_code : str
        Volunteer identifier (used in filename).
    output_dir : str, optional
        Directory to save the file in. Defaults to current directory.
    algorithm : str, optional
        "context tree" (default) or "pseudo-random", used in the filename.
    """
    if algorithm == "context tree":
        prefix = "tree_sequence"
    elif algorithm == "pseudo-random":
        prefix = "pseudo_random_sequence"
    else:
        raise ValueError(f"Unknown sequence algorithm: {algorithm!r}")

    filename = (
        f"{output_dir}/{prefix}_{n_stimuli}_trials_{volunteer_code}.txt"
    )
    np.savetxt(filename, sequence, delimiter=",", fmt="%d")
    print(f"Sequence exported to {filename}")

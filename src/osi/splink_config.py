"""Canonical Splink settings for the Cuyahoga entity-resolution pipeline.

Both the golden dataset test and the production pipeline import
``build_settings`` so the blocking rules, comparison levels, and thresholds
cannot drift apart.

The column names below are the canonical names used by the pipeline.  Input
adapters (see ``splink_graph_pipeline.load_persons``) are responsible for
mapping source columns such as ``surname`` or ``date_of_birth`` onto these
names.
"""

from __future__ import annotations

import splink.comparison_library as cl
from splink import SettingsCreator, block_on


# Jaro-Winkler thresholds validated by the golden dataset test.
JARO_WINKLER_THRESHOLDS = [0.92, 0.85, 0.80]

# The four blocking rules used by the golden test.  Keep this list small:
# adding rules increases the number of candidate pairs super-linearly.
BLOCKING_RULES = (
    ("last_name", "first_name"),
    ("last_name", "dob"),
    ("last_name", "zip_code"),
    ("first_name", "dob"),
)


def build_settings(*, pin_middle_initial: bool = True) -> SettingsCreator:
    """Return the validated Splink settings.

    Parameters
    ----------
    pin_middle_initial:
        When true, seed the sparse ``middle_initial`` comparison with
        conservative m/u values.  This is required for the 20-row golden test,
        where EM would otherwise assign a degenerate weight.  Production runs
        EM after construction, which overwrites these seeds with estimates
        from the full dataset.
    """

    middle_initial = cl.ExactMatch("middle_initial").configure(
        term_frequency_adjustments=True
    )
    if pin_middle_initial:
        middle_initial = cl.ExactMatch("middle_initial").configure(
            term_frequency_adjustments=True,
            m_probabilities=[0.8, 0.2],
            u_probabilities=[0.3, 0.7],
        )

    return SettingsCreator(
        link_type="dedupe_only",
        unique_id_column_name="unique_id",
        retain_intermediate_calculation_columns=True,
        retain_matching_columns=True,
        em_convergence=0.001,
        max_iterations=20,
        blocking_rules_to_generate_predictions=[
            block_on(*rule) for rule in BLOCKING_RULES
        ],
        comparisons=[
            # Handles swapped forename/surname and applies term frequency to
            # the concatenated full name.
            cl.ForenameSurnameComparison(
                "first_name",
                "last_name",
                forename_surname_concat_col_name="full_name",
            ),
            cl.JaroWinklerAtThresholds(
                "last_name", JARO_WINKLER_THRESHOLDS
            ),
            cl.JaroWinklerAtThresholds(
                "first_name", JARO_WINKLER_THRESHOLDS
            ),
            # Exact DOB plus tight fuzzy levels: +/-1 day, +/-1 month,
            # +/-10 years.
            cl.DateOfBirthComparison(
                "dob",
                input_is_string=True,
                datetime_thresholds=[1, 1, 10],
                datetime_metrics=["day", "month", "year"],
                invalid_dates_as_null=True,
            ),
            middle_initial,
            cl.ExactMatch("address").configure(
                term_frequency_adjustments=True
            ),
            cl.ExactMatch("zip_code").configure(
                term_frequency_adjustments=True
            ),
            cl.ExactMatch("voter_id").configure(
                term_frequency_adjustments=True
            ),
        ],
    )

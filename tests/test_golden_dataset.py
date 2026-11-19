"""Pytest entry point for the golden dataset validation.

The detailed report lives in ``golden_dataset_test.py``; this wrapper makes the
validation part of the normal test suite. Run the script directly to also
generate the Cluster Studio dashboard.
"""

from golden_dataset_test import run_golden_test


def test_golden_dataset_clusters():
    result = run_golden_test(generate_dashboard=False)
    clusters_df = result["clusters_df"]

    assert len(clusters_df) == 20, "every input record must be clustered"
    assert clusters_df["cluster_id"].nunique() == 17, (
        "expected 17 conservative clusters"
    )

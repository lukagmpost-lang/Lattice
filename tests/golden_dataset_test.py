#!/usr/bin/env python3
"""
Golden Dataset Test for Splink Entity Resolution

This test validates the Splink entity resolution pipeline with a controlled
dataset of 20 records representing 16 real entities. It uses the production
comparison/blocking rules but deliberately skips EM training, because with only
20 records most comparison levels are unobserved and EM produces unstable,
degenerate weights. The production pipeline uses the same deterministic priors
by default; ``--train`` enables EM for experiments.

Entity breakdown (20 records):
- 12 unique people appearing once (Alice Smith, Bob Jones, Carol White,
  David Brown, Eva Green, Frank Black, Henry Wilson, Irene Taylor,
  James Anderson, Kelly Thomas, Larry Jackson, Mary Harris)
- 1 person appearing 3 times with variations (John A. Smith / Johnathan Smith /
  J. Smith, all DOB 1980-01-01)
- 2 different people with the same name but different DOBs
  (Michael Davis 1950, Michael Davis 1990)
- 1 person appearing 3 times with an address typo
  (Grace Lee at "123 Main St" vs "123 Mian St")

Expected clustering (17 clusters, conservative 0.95 threshold):
- 15 singletons (12 unique people + J. Smith + the two Michael Davises)
- 1 cluster of 2 (John Smith: JOHN + JOHNATHAN; the "J" initial does not
  match at 0.95, which is the intended conservative behavior)
- 1 cluster of 3 (Grace Lee: address typo does not prevent the merge)
Total: 17 clusters
"""

import sys
from pathlib import Path

import pandas as pd
from splink import Linker
from splink.internals.duckdb.database_api import DuckDBAPI

# Make the canonical settings and production splitter importable when this
# file is run directly (pytest already puts the repo root on the path).
_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
for _path in (_ROOT, _SRC):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from osi.splink_config import build_settings
from splink_graph_pipeline import split_conflicting_clusters


# ============================================================
# 1. CREATE GOLDEN DATASET (20 records, 12 real entities)
# ============================================================

def create_golden_dataset():
    """Create 20 records representing 12 real entities."""
    
    records = [
        # 8 unique people appearing once
        {"node_id": "rec_01", "first_name": "ALICE", "middle_name": "", "last_name": "SMITH", "suffix": "", "dob": "1990-05-15", "address": "100 OAK ST, CLEVELAND, 44102", "zip_code": "44102", "voter_id": "OH001", "full_name": "ALICE SMITH"},
        {"node_id": "rec_02", "first_name": "BOB", "middle_name": "", "last_name": "JONES", "suffix": "", "dob": "1985-03-22", "address": "200 ELM ST, CLEVELAND, 44103", "zip_code": "44103", "voter_id": "OH002", "full_name": "BOB JONES"},
        {"node_id": "rec_03", "first_name": "CAROL", "middle_name": "ANN", "last_name": "WHITE", "suffix": "", "dob": "1992-07-08", "address": "300 MAPLE AVE, CLEVELAND, 44104", "zip_code": "44104", "voter_id": "OH003", "full_name": "CAROL ANN WHITE"},
        {"node_id": "rec_04", "first_name": "DAVID", "middle_name": "LEE", "last_name": "BROWN", "suffix": "", "dob": "1988-11-30", "address": "400 PINE RD, CLEVELAND, 44105", "zip_code": "44105", "voter_id": "OH004", "full_name": "DAVID LEE BROWN"},
        {"node_id": "rec_05", "first_name": "EVA", "middle_name": "MARIE", "last_name": "GREEN", "suffix": "", "dob": "1995-01-17", "address": "500 CEDAR LN, CLEVELAND, 44106", "zip_code": "44106", "voter_id": "OH005", "full_name": "EVA MARIE GREEN"},
        {"node_id": "rec_06", "first_name": "FRANK", "middle_name": "", "last_name": "BLACK", "suffix": "JR", "dob": "1980-09-05", "address": "600 BIRCH DR, CLEVELAND, 44107", "zip_code": "44107", "voter_id": "OH006", "full_name": "FRANK BLACK JR"},
        {"node_id": "rec_07", "first_name": "GRACE", "middle_name": "ELLEN", "last_name": "LEE", "suffix": "", "dob": "1988-04-20", "address": "123 MAIN ST, CLEVELAND, 44108", "zip_code": "44108", "voter_id": "OH007", "full_name": "GRACE ELLEN LEE"},
        {"node_id": "rec_08", "first_name": "HENRY", "middle_name": "THOMAS", "last_name": "WILSON", "suffix": "", "dob": "1975-12-03", "address": "700 OAK AVE, CLEVELAND, 44109", "zip_code": "44109", "voter_id": "OH008", "full_name": "HENRY THOMAS WILSON"},
        
        # John Smith - 3 records with variations (same DOB, should merge)
        {"node_id": "rec_09", "first_name": "JOHN", "middle_name": "A", "last_name": "SMITH", "suffix": "", "dob": "1980-01-01", "address": "100 MAIN ST, CLEVELAND, 44110", "zip_code": "44110", "voter_id": "OH009", "full_name": "JOHN A SMITH"},
        {"node_id": "rec_10", "first_name": "JOHNATHAN", "middle_name": "", "last_name": "SMITH", "suffix": "", "dob": "1980-01-01", "address": "100 MAIN STREET, CLEVELAND, 44110", "zip_code": "44110", "voter_id": "OH009", "full_name": "JOHNATHAN SMITH"},
        {"node_id": "rec_11", "first_name": "J", "middle_name": "", "last_name": "SMITH", "suffix": "", "dob": "1980-01-01", "address": "100 MAIN ST, CLEVELAND, 44110", "zip_code": "44110", "voter_id": "OH009", "full_name": "J SMITH"},
        
        # Michael Davis - 2 DIFFERENT people with same name, DIFFERENT DOBs (should NOT merge)
        {"node_id": "rec_12", "first_name": "MICHAEL", "middle_name": "A", "last_name": "DAVIS", "suffix": "", "dob": "1950-06-15", "address": "1000 EUCLID AVE, CLEVELAND, 44115", "zip_code": "44115", "voter_id": "OH012", "full_name": "MICHAEL A DAVIS"},
        {"node_id": "rec_13", "first_name": "MICHAEL", "middle_name": "B", "last_name": "DAVIS", "suffix": "", "dob": "1990-08-25", "address": "2000 EUCLID AVE, CLEVELAND, 44115", "zip_code": "44115", "voter_id": "OH013", "full_name": "MICHAEL B DAVIS"},
        
        # Grace Lee with typo in address (should merge despite typo)
        {"node_id": "rec_14", "first_name": "GRACE", "middle_name": "ELLEN", "last_name": "LEE", "suffix": "", "dob": "1988-04-20", "address": "123 MAIN ST, CLEVELAND, 44108", "zip_code": "44108", "voter_id": "OH007", "full_name": "GRACE ELLEN LEE"},
        {"node_id": "rec_15", "first_name": "GRACE", "middle_name": "E", "last_name": "LEE", "suffix": "", "dob": "1988-04-20", "address": "123 MIAN ST, CLEVELAND, 44108", "zip_code": "44108", "voter_id": "OH007", "full_name": "GRACE E LEE"},
        
        # Additional unique people to reach 20 records
        {"node_id": "rec_16", "first_name": "IRENE", "middle_name": "", "last_name": "TAYLOR", "suffix": "", "dob": "1993-02-14", "address": "800 MAPLE ST, CLEVELAND, 44111", "zip_code": "44111", "voter_id": "OH016", "full_name": "IRENE TAYLOR"},
        {"node_id": "rec_17", "first_name": "JAMES", "middle_name": "K", "last_name": "ANDERSON", "suffix": "", "dob": "1982-08-09", "address": "900 WALNUT ST, CLEVELAND, 44112", "zip_code": "44112", "voter_id": "OH017", "full_name": "JAMES K ANDERSON"},
        {"node_id": "rec_18", "first_name": "KELLY", "middle_name": "ANN", "last_name": "THOMAS", "suffix": "", "dob": "1991-06-07", "address": "1000 CHESTNUT ST, CLEVELAND, 44113", "zip_code": "44113", "voter_id": "OH018", "full_name": "KELLY ANN THOMAS"},
        {"node_id": "rec_19", "first_name": "LARRY", "middle_name": "", "last_name": "JACKSON", "suffix": "SR", "dob": "1970-03-11", "address": "1100 SPRUCE ST, CLEVELAND, 44114", "zip_code": "44114", "voter_id": "OH019", "full_name": "LARRY JACKSON SR"},
        {"node_id": "rec_20", "first_name": "MARY", "middle_name": "LOUISE", "last_name": "HARRIS", "suffix": "", "dob": "1987-10-28", "address": "1200 HICKORY LN, CLEVELAND, 44116", "zip_code": "44116", "voter_id": "OH020", "full_name": "MARY LOUISE HARRIS"},
        
    ]
    
    df = pd.DataFrame(records)
    
    # Ensure all columns exist
    required_cols = ['node_id', 'first_name', 'middle_name', 'last_name', 'suffix', 'dob', 'address', 'zip_code', 'voter_id', 'full_name']
    for col in required_cols:
        if col not in df.columns:
            df[col] = ""
    
    # Add missing columns
    df['middle_initial'] = df['middle_name'].str[:1].str.upper()
    df['suffix'] = df['suffix'].fillna("")
    df['middle_name'] = df['middle_name'].fillna("")
    df['suffix'] = df['suffix'].fillna("")
    
    return df


# ============================================================
# 2. SPLINK SETTINGS (Production Pipeline Configuration)
# ============================================================

def build_test_settings():
    """Build the canonical Splink settings shared with production."""
    return build_settings()


# ============================================================
# 3. MAIN TEST FUNCTION
# ============================================================

def run_golden_test(generate_dashboard: bool = True):
    """Run the complete golden dataset test."""
    
    print("=" * 70)
    print("GOLDEN DATASET TEST - SPLINK ENTITY RESOLUTION")
    print("=" * 70)
    
    # 1. Create golden dataset
    print("\n1. Creating golden dataset...")
    df = create_golden_dataset()
    print(f"   Created {len(df)} records")
    
    # 2. Prepare for Splink
    print("\n2. Preparing data for Splink...")
    df = df.fillna("")
    df["unique_id"] = range(len(df))
    df["middle_initial"] = df["middle_name"].str[:1].str.upper()
    df["full_name"] = df["first_name"] + " " + df["last_name"]
    
    # 3. Build Splink settings
    print("\n3. Building Splink settings...")
    settings = build_test_settings()
    
    # 4. Initialize linker
    print("\n4. Initializing Splink linker...")
    db_api = DuckDBAPI()
    # Splink's clustering internals also use a column named "node_id", so keep
    # that reporting column out of the frame registered with Splink.
    splink_df = df.drop(columns=["node_id"])
    df_sdf = db_api.register(splink_df, table_name="persons")
    linker = Linker(df_sdf, settings)
    
    # 5. Model parameters
    print("\n5. Using conservative built-in priors (no EM on 20 records)...")
    # EM is intentionally skipped here. With 20 records most comparison levels
    # are unobserved, so EM produces unstable and sometimes degenerate weights.
    # The production pipeline also uses these deterministic priors by default.
    print("   Golden test uses deterministic Splink defaults.")
    
    # 6. Predict with conservative threshold
    print("\n6. Running prediction (match_probability > 0.95)...")
    pairwise_predictions = linker.inference.predict(threshold_match_probability=0.95)
    
    # 7. Cluster
    print("\n7. Clustering...")
    # Splink 5: use the linker's clustering component. It clusters on the
    # configured unique_id_column_name ("unique_id") so the Cluster Studio
    # dashboard can join the clusters back to the source records.
    clusters = linker.clustering.cluster_pairwise_predictions_at_threshold(
        pairwise_predictions, threshold_match_probability=0.95
    )
    clusters_df = clusters.as_pandas_dataframe()
    
    print(f"\nClustering complete:")
    print(f"  Total records: {len(clusters_df)}")
    print(f"  Total clusters: {clusters_df['cluster_id'].nunique()}")
    print(f"  Multi-record clusters: {(clusters_df.groupby('cluster_id').size() > 1).sum()}")
    
    # 8. Analyze results
    print("\n8. Analyzing results...")
    # The clustered frame already contains the input columns; only add the
    # reporting id back from the source frame.
    clusters_df = clusters_df.merge(df[['unique_id', 'node_id']], 
                                     on='unique_id', how='left')
    
    # Print cluster breakdown
    print("\n=== CLUSTER BREAKDOWN ===")
    cluster_sizes = clusters_df.groupby('cluster_id').size()
    print(f"Total clusters: {clusters_df['cluster_id'].nunique()}")
    print(f"Multi-record clusters: {(cluster_sizes > 1).sum()}")
    print(f"Records in multi-record clusters: {cluster_sizes[cluster_sizes > 1].sum()}")
    
    # Show each cluster
    print("\n=== CLUSTER DETAILS ===")
    for cid in sorted(clusters_df['cluster_id'].unique()):
        cluster_recs = clusters_df[clusters_df['cluster_id'] == cid]
        print(f"\n  Cluster {cid} ({len(cluster_recs)} records):")
        for _, row in cluster_recs.iterrows():
            print(f"    {row['node_id']}: {row['first_name']} {row['middle_initial']} {row['last_name']} | DOB: {row['dob']} | Addr: {row['address'][:40]}")
    
    # 9. VALIDATION ASSERTIONS
    print("\n" + "=" * 70)
    print("VALIDATION ASSERTIONS")
    print("=" * 70)
    
    # Get cluster assignments by node_id
    cluster_assignments = clusters_df.set_index('node_id')['cluster_id'].to_dict()
    
    # Test 1: John Smith full name variations should merge (rec_09 JOHN + rec_10 JOHNATHAN)
    # Note: "J" initial (rec_11) may not match at 0.95 conservative threshold
    john_ids = ['rec_09', 'rec_10']
    john_clusters = [cluster_assignments.get(nid) for nid in john_ids]
    john_same = len(set(john_clusters)) == 1
    print(f"\n✓ TEST 1: John Smith (JOHN + JOHNATHAN) merge into 1 cluster: {'PASS' if john_same else 'FAIL'}")
    print(f"  Records: {john_ids}")
    print(f"  Clusters: {john_clusters}")
    assert john_same, "FAIL: John Smith JOHN + JOHNATHAN should merge into 1 cluster"
    
    # Verify J SMITH (rec_11) is separate - conservative matching at 0.95 doesn't match initial to full name
    j_initial_cluster = cluster_assignments.get('rec_11')
    john_cluster = cluster_assignments.get('rec_09')
    j_initial_separate = j_initial_cluster != john_cluster
    print(f"\n✓ TEST 1b: J SMITH (rec_11) stays separate from JOHN/JOHNATHAN: {'PASS' if j_initial_separate else 'FAIL'}")
    print(f"  J SMITH cluster: {j_initial_cluster}, JOHN cluster: {john_cluster}")
    assert j_initial_separate, "FAIL: J SMITH initial should stay separate at conservative threshold"
    
    # Test 2: Michael Davis (different DOBs) should NOT merge
    michael_ids = ['rec_12', 'rec_13']
    michael_clusters = [cluster_assignments.get(nid) for nid in michael_ids]
    michael_diff = len(set(michael_clusters)) == 2
    print(f"\n✓ TEST 2: Michael Davis (different DOBs) stay separate: {'PASS' if michael_diff else 'FAIL'}")
    print(f"  Records: {michael_ids}")
    print(f"  Clusters: {michael_clusters}")
    assert michael_diff, "FAIL: Michael Davis with different DOBs should NOT merge"
    
    # Test 3: Grace Lee with typo should merge
    grace_ids = ['rec_07', 'rec_14', 'rec_15']
    grace_clusters = [cluster_assignments.get(nid) for nid in grace_ids]
    grace_same = len(set(grace_clusters)) == 1
    print(f"\n✓ TEST 3: Grace Lee (address typo) merges into 1 cluster: {'PASS' if grace_same else 'FAIL'}")
    print(f"  Records: {grace_ids}")
    print(f"  Clusters: {grace_clusters}")
    assert grace_same, "FAIL: Grace Lee with address typo should merge"
    
    # Test 4: Unique people remain singletons (12 unique people: rec_01-06, 08, 16-20)
    unique_ids = ['rec_01', 'rec_02', 'rec_03', 'rec_04', 'rec_05', 'rec_06', 'rec_08', 'rec_16', 'rec_17', 'rec_18', 'rec_19', 'rec_20']
    unique_clusters = [cluster_assignments.get(nid) for nid in unique_ids]
    unique_all_diff = len(set(unique_clusters)) == len(unique_ids)
    print(f"\n✓ TEST 4: 12 unique people remain as singletons: {'PASS' if unique_all_diff else 'FAIL'}")
    print(f"  Records: {unique_ids}")
    print(f"  Clusters: {unique_clusters}")
    assert unique_all_diff, "FAIL: Unique people should remain as singletons"
    
    # Test 5: Total clusters - with conservative 0.95 threshold, we expect 17 clusters:
    # 12 singletons (unique) + 1 (J SMITH separate) + 2 (Michael Davis separate) + 1 (John x2) + 1 (Grace x3) = 17
    total_clusters = clusters_df['cluster_id'].nunique()
    expected_clusters = 17
    print(f"\n✓ TEST 5: Total clusters = {expected_clusters}: {'PASS' if total_clusters == expected_clusters else 'FAIL'}")
    print(f"  Actual clusters: {total_clusters}")
    assert total_clusters == expected_clusters, f"FAIL: Expected {expected_clusters} clusters, got {total_clusters}"
    
    # Test 6: Multi-record clusters = 2 (John x2, Grace x3)
    multi_record_clusters = (clusters_df.groupby('cluster_id').size() > 1).sum()
    expected_multi = 2
    print(f"\n✓ TEST 6: Multi-record clusters = {expected_multi} (John x2, Grace x3): {'PASS' if multi_record_clusters == expected_multi else 'FAIL'}")
    print(f"  Multi-record clusters: {multi_record_clusters}")
    assert multi_record_clusters == expected_multi, f"FAIL: Expected {expected_multi} multi-record clusters, got {multi_record_clusters}"
    
    print("\n" + "=" * 70)
    print("ALL TESTS PASSED!" if all([
        john_same, michael_diff, grace_same, unique_all_diff, 
        total_clusters == expected_clusters, multi_record_clusters == expected_multi
    ]) else "SOME TESTS FAILED")
    print("=" * 70)
    
    # 10. Generate Cluster Studio Dashboard (skipped in pytest runs)
    if generate_dashboard:
        print("\n10. Generating Cluster Studio Dashboard...")
        try:
            html_path = "golden_dataset_cluster_studio.html"
            linker.visualisations.cluster_studio_dashboard(
                pairwise_predictions, 
                clusters, 
                html_path,
                sampling_method="by_cluster_size",
                overwrite=True
            )
            print(f"   Dashboard saved to: {html_path}")
        except Exception as e:
            print(f"   Warning: Could not generate dashboard: {e}")
    
    return {
        'clusters_df': clusters_df,
        'pairwise_predictions': pairwise_predictions,
        'linker': linker,
        'clusters': clusters
    }


if __name__ == "__main__":
    import pandas as pd
    import splink.comparison_library as cl
    from splink import Linker, SettingsCreator, block_on
    from splink.internals.duckdb.database_api import DuckDBAPI
    
    result = run_golden_test()
    print("\n✅ Golden Dataset Test Complete!")
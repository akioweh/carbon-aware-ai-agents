"""
Carbon Intensity Data Analysis & Preprocessing Exploration.

Standalone script that loads from carbon_intensity.db, runs analysis,
and outputs graphs + markdown report to docs/.
"""

import sqlite3
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

# ── Constants ────────────────────────────────────────────────────────────

DB_PATH = Path(__file__).parent / "carbon_intensity.db"
DOCS_DIR = Path(__file__).parent.parent / "docs"

REGION_TO_DC = {
    'London':             'Data-Center-1',
    'South East England': 'Data-Center-2',
    'South Yorkshire':    'Data-Center-3',
    'North West England': 'Data-Center-4',
    'North East England': 'Data-Center-5',
}

REGIONS = list(REGION_TO_DC.keys())
DPI = 150


# ── Step 1: Data Loading ────────────────────────────────────────────────

def load_data() -> pd.DataFrame:
    """Load carbon intensity readings from SQLite."""
    if not DB_PATH.exists():
        print(f"ERROR: Database not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT r.name AS region, cr.timestamp_from AS ts, cr.actual
        FROM carbon_readings cr
        JOIN regions r ON cr.region_id = r.region_id
        WHERE cr.actual IS NOT NULL
    """, conn)
    conn.close()

    df['ts'] = pd.to_datetime(df['ts'])
    df = df.drop_duplicates(subset=['region', 'ts']).sort_values(['region', 'ts']).reset_index(drop=True)
    return df


# ── Step 2: Descriptive Statistics ──────────────────────────────────────

def descriptive_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Per-region descriptive statistics."""
    stats = []
    for region in REGIONS:
        rd = df[df['region'] == region]['actual']
        stats.append({
            'Region': region,
            'DC': REGION_TO_DC[region],
            'Count': len(rd),
            'Mean': rd.mean(),
            'Median': rd.median(),
            'Std': rd.std(),
            'Min': rd.min(),
            'Max': rd.max(),
            'Q25': rd.quantile(0.25),
            'Q75': rd.quantile(0.75),
            'CV': rd.std() / rd.mean() if rd.mean() != 0 else 0,
        })
    return pd.DataFrame(stats)


# ── Step 3: Week-to-Week Analysis ───────────────────────────────────────

def week_analysis(df: pd.DataFrame):
    """Partition into ISO weeks, compute per-slot stats and week-to-week diffs."""
    results = {}
    for region in REGIONS:
        rd = df[df['region'] == region].copy()
        rd['iso_year'] = rd['ts'].dt.isocalendar().year.astype(int)
        rd['iso_week'] = rd['ts'].dt.isocalendar().week.astype(int)
        rd['weekday'] = rd['ts'].dt.weekday  # 0=Mon
        rd['half_hour'] = rd['ts'].dt.hour * 2 + rd['ts'].dt.minute // 30
        rd['slot'] = rd['weekday'] * 48 + rd['half_hour']  # 0..335

        # Group by (year, week)
        week_keys = rd.groupby(['iso_year', 'iso_week']).size().reset_index(name='count')
        # Drop incomplete weeks
        week_keys = week_keys[week_keys['count'] >= 300]

        if len(week_keys) == 0:
            results[region] = None
            continue

        # Build slot × week matrix
        pivot = rd.pivot_table(index='slot', columns=['iso_year', 'iso_week'],
                               values='actual', aggfunc='mean')
        # Only keep complete weeks
        valid_cols = [(y, w) for y, w in zip(week_keys['iso_year'], week_keys['iso_week'])]
        pivot = pivot[[c for c in pivot.columns if c in valid_cols]]

        slot_mean = pivot.mean(axis=1)
        slot_std = pivot.std(axis=1)

        # Consecutive-week diffs
        sorted_cols = sorted(pivot.columns)
        diffs = []
        for i in range(1, len(sorted_cols)):
            d = (pivot[sorted_cols[i]] - pivot[sorted_cols[i - 1]]).abs()
            diffs.append(d)
        if diffs:
            diff_df = pd.concat(diffs, axis=1)
            diff_mean = diff_df.mean(axis=1)
            diff_std = diff_df.std(axis=1)
        else:
            diff_mean = pd.Series(dtype=float)
            diff_std = pd.Series(dtype=float)

        # Per-week summary
        week_summaries = []
        for col in sorted_cols:
            vals = pivot[col].dropna()
            week_summaries.append({
                'year': col[0], 'week': col[1],
                'mean': vals.mean(), 'std': vals.std(),
                'slots': len(vals),
            })

        results[region] = {
            'slot_mean': slot_mean,
            'slot_std': slot_std,
            'diff_mean': diff_mean,
            'diff_std': diff_std,
            'week_summaries': week_summaries,
            'pivot': pivot,
        }
    return results


def find_volatile_slots(week_data: dict) -> list:
    """Identify most volatile day/hour combinations across regions."""
    volatile = []
    for region, data in week_data.items():
        if data is None:
            continue
        std = data['slot_std']
        if len(std) == 0:
            continue
        top5 = std.nlargest(5)
        for slot, val in top5.items():
            day = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][slot // 48]
            hour = (slot % 48) // 2
            minute = (slot % 2) * 30
            volatile.append({
                'region': region, 'slot': slot,
                'day': day, 'time': f"{hour:02d}:{minute:02d}",
                'std': val,
            })
    return sorted(volatile, key=lambda x: x['std'], reverse=True)[:15]


# ── Step 4: Graphs ──────────────────────────────────────────────────────

def get_two_recent_complete_weeks(df: pd.DataFrame, region: str):
    """Return data for the 2 most recent complete ISO weeks."""
    rd = df[df['region'] == region].copy()
    rd['iso_year'] = rd['ts'].dt.isocalendar().year.astype(int)
    rd['iso_week'] = rd['ts'].dt.isocalendar().week.astype(int)
    counts = rd.groupby(['iso_year', 'iso_week']).size().reset_index(name='count')
    complete = counts[counts['count'] >= 300].sort_values(['iso_year', 'iso_week'])
    if len(complete) < 2:
        return None, None
    w1y, w1w = complete.iloc[-2][['iso_year', 'iso_week']]
    w2y, w2w = complete.iloc[-1][['iso_year', 'iso_week']]
    d1 = rd[(rd['iso_year'] == w1y) & (rd['iso_week'] == w1w)].sort_values('ts')
    d2 = rd[(rd['iso_year'] == w2y) & (rd['iso_week'] == w2w)].sort_values('ts')
    return d1, d2


def plot_raw_comparison(df: pd.DataFrame):
    """4a: Raw 2-week comparison, 5 rows × 2 cols."""
    print("  Generating raw comparison plot...")
    fig, axes = plt.subplots(5, 2, figsize=(16, 17.5), sharey='row')
    fig.suptitle('Carbon Intensity: 2-Week Raw Comparison', fontsize=14, y=0.98)

    for i, region in enumerate(REGIONS):
        w1, w2 = get_two_recent_complete_weeks(df, region)
        for j, (week_df, label) in enumerate([(w1, 'Week -2'), (w2, 'Week -1')]):
            ax = axes[i, j]
            if week_df is None or len(week_df) == 0:
                ax.text(0.5, 0.5, 'No data', transform=ax.transAxes, ha='center')
                continue
            ax.plot(week_df['ts'], week_df['actual'], linewidth=0.7, color='C0')
            ax.set_title(f"{region} — {label}", fontsize=9)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%a'))
            ax.xaxis.set_major_locator(mdates.DayLocator())
            ax.tick_params(axis='x', labelsize=7)
            ax.tick_params(axis='y', labelsize=7)
            if j == 0:
                ax.set_ylabel('gCO₂/kWh', fontsize=8)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    path = DOCS_DIR / 'analysis_raw_comparison.png'
    fig.savefig(path, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f"    Saved: {path}")


def plot_smoothing(df: pd.DataFrame):
    """4b: Smoothing overlays for 2 weeks of data per region."""
    print("  Generating smoothing overlay plot...")
    fig, axes = plt.subplots(5, 1, figsize=(16, 17.5))
    fig.suptitle('Carbon Intensity: Smoothing Overlays (2 Weeks)', fontsize=14, y=0.98)

    for i, region in enumerate(REGIONS):
        ax = axes[i]
        _, w2 = get_two_recent_complete_weeks(df, region)
        # Use 2 weeks: combine both
        w1, w2 = get_two_recent_complete_weeks(df, region)
        if w1 is not None and w2 is not None:
            two_weeks = pd.concat([w1, w2]).sort_values('ts').set_index('ts')
        elif w2 is not None:
            two_weeks = w2.sort_values('ts').set_index('ts')
        else:
            ax.text(0.5, 0.5, 'No data', transform=ax.transAxes, ha='center')
            continue

        series = two_weeks['actual']
        ax.plot(series.index, series.values, linewidth=0.5, alpha=0.5, color='gray', label='Raw')
        # MA-3h (window=6 half-hours)
        ma3 = series.rolling(window=6, center=True).mean()
        ax.plot(ma3.index, ma3.values, linewidth=1, label='MA-3h')
        # MA-24h (window=48)
        ma24 = series.rolling(window=48, center=True).mean()
        ax.plot(ma24.index, ma24.values, linewidth=1.2, label='MA-24h')
        # EWMA-24h (span=48)
        ewma = series.ewm(span=48).mean()
        ax.plot(ewma.index, ewma.values, linewidth=1, linestyle='--', label='EWMA-24h')

        ax.set_title(f"{region}", fontsize=10)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%a %d'))
        ax.xaxis.set_major_locator(mdates.DayLocator())
        ax.tick_params(axis='x', labelsize=7)
        ax.tick_params(axis='y', labelsize=7)
        ax.set_ylabel('gCO₂/kWh', fontsize=8)
        ax.legend(fontsize=7, loc='upper right')

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    path = DOCS_DIR / 'analysis_smoothing.png'
    fig.savefig(path, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f"    Saved: {path}")


def plot_derivatives(df: pd.DataFrame):
    """4c: Derivative signals — diff(1) and diff(48)."""
    print("  Generating derivatives plot...")
    fig, axes = plt.subplots(5, 2, figsize=(16, 17.5), sharey='row')
    fig.suptitle('Carbon Intensity: Derivative Signals (2 Weeks)', fontsize=14, y=0.98)

    for i, region in enumerate(REGIONS):
        w1, w2 = get_two_recent_complete_weeks(df, region)
        if w1 is not None and w2 is not None:
            two_weeks = pd.concat([w1, w2]).sort_values('ts').set_index('ts')
        elif w2 is not None:
            two_weeks = w2.sort_values('ts').set_index('ts')
        else:
            for j in range(2):
                axes[i, j].text(0.5, 0.5, 'No data', transform=axes[i, j].transAxes, ha='center')
            continue

        series = two_weeks['actual']

        # diff(1): 30-min rate of change
        d1 = series.diff(1)
        axes[i, 0].plot(d1.index, d1.values, linewidth=0.6, color='C1')
        axes[i, 0].axhline(0, color='gray', linewidth=0.5, linestyle='--')
        axes[i, 0].set_title(f"{region} — diff(1): 30-min Δ", fontsize=9)
        axes[i, 0].xaxis.set_major_formatter(mdates.DateFormatter('%a'))
        axes[i, 0].xaxis.set_major_locator(mdates.DayLocator())
        axes[i, 0].tick_params(axis='x', labelsize=7)
        axes[i, 0].tick_params(axis='y', labelsize=7)
        if i == 2:
            axes[i, 0].set_ylabel('Δ gCO₂/kWh', fontsize=8)

        # diff(48): day-over-day same-time difference
        d48 = series.diff(48)
        axes[i, 1].plot(d48.index, d48.values, linewidth=0.6, color='C2')
        axes[i, 1].axhline(0, color='gray', linewidth=0.5, linestyle='--')
        axes[i, 1].set_title(f"{region} — diff(48): Day-over-Day Δ", fontsize=9)
        axes[i, 1].xaxis.set_major_formatter(mdates.DateFormatter('%a'))
        axes[i, 1].xaxis.set_major_locator(mdates.DayLocator())
        axes[i, 1].tick_params(axis='x', labelsize=7)
        axes[i, 1].tick_params(axis='y', labelsize=7)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    path = DOCS_DIR / 'analysis_derivatives.png'
    fig.savefig(path, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f"    Saved: {path}")


def plot_stl(df: pd.DataFrame):
    """4d: STL decomposition — trend / seasonal / residual per region."""
    print("  Generating STL decomposition plot...")
    fig, axes = plt.subplots(5, 3, figsize=(18, 17.5))
    fig.suptitle('STL Decomposition (period=48, 30-min intervals)', fontsize=14, y=0.98)
    labels = ['Trend', 'Seasonal', 'Residual']

    for i, region in enumerate(REGIONS):
        rd = df[df['region'] == region].copy().sort_values('ts')
        # Resample to regular 30-min grid with interpolation
        rd = rd.set_index('ts')
        regular = rd['actual'].resample('30min').mean().interpolate(method='linear')

        if len(regular.dropna()) < 96:  # need at least 2 days
            for j in range(3):
                axes[i, j].text(0.5, 0.5, 'Insufficient data', transform=axes[i, j].transAxes, ha='center')
            continue

        regular = regular.dropna()
        stl = STL(regular, period=48, robust=True)
        result = stl.fit()

        components = [result.trend, result.seasonal, result.resid]
        colors = ['C0', 'C1', 'C3']
        for j, (comp, label, color) in enumerate(zip(components, labels, colors)):
            axes[i, j].plot(comp.index, comp.values, linewidth=0.6, color=color)
            if i == 0:
                axes[i, j].set_title(label, fontsize=11, fontweight='bold')
            axes[i, j].tick_params(axis='x', labelsize=6)
            axes[i, j].tick_params(axis='y', labelsize=7)
            axes[i, j].xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
            axes[i, j].xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
            if j == 0:
                axes[i, j].set_ylabel(region, fontsize=8, rotation=90)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    path = DOCS_DIR / 'analysis_stl_decomposition.png'
    fig.savefig(path, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f"    Saved: {path}")


def plot_weekly_variance_heatmap(week_data: dict):
    """4e: Weekly variance heatmap — x=336 slots, y=regions."""
    print("  Generating weekly variance heatmap...")
    fig, ax = plt.subplots(figsize=(18, 5))

    matrix = np.full((len(REGIONS), 336), np.nan)
    for i, region in enumerate(REGIONS):
        data = week_data[region]
        if data is None:
            continue
        std = data['slot_std']
        for slot in std.index:
            if 0 <= slot < 336:
                matrix[i, slot] = std[slot]

    im = ax.imshow(matrix, aspect='auto', cmap='YlOrRd', interpolation='nearest')
    ax.set_yticks(range(len(REGIONS)))
    ax.set_yticklabels(REGIONS, fontsize=8)

    # Label x-axis by day
    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    day_ticks = [d * 48 + 24 for d in range(7)]
    ax.set_xticks(day_ticks)
    ax.set_xticklabels(day_names, fontsize=9)

    # Add day separators
    for d in range(1, 7):
        ax.axvline(d * 48 - 0.5, color='white', linewidth=1)

    cbar = fig.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label('Week-to-Week SD (gCO₂/kWh)', fontsize=9)
    ax.set_title('Weekly Variance by Time Slot and Region', fontsize=12)
    ax.set_xlabel('Time of Week', fontsize=10)

    plt.tight_layout()
    path = DOCS_DIR / 'analysis_weekly_variance.png'
    fig.savefig(path, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f"    Saved: {path}")


# ── Step 5: Markdown Report ─────────────────────────────────────────────

def generate_report(df: pd.DataFrame, desc_stats: pd.DataFrame,
                    week_data: dict, volatile_slots: list):
    """Generate markdown report."""
    print("  Generating markdown report...")
    lines = []
    lines.append("# Carbon Intensity Data Analysis Report\n")
    lines.append(f"*Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}*\n")

    # Data overview
    lines.append("## Data Overview\n")
    date_min = df['ts'].min().strftime('%Y-%m-%d')
    date_max = df['ts'].max().strftime('%Y-%m-%d')
    lines.append(f"- **Date range**: {date_min} to {date_max}")
    lines.append(f"- **Total readings**: {len(df):,}")
    lines.append(f"- **Regions**: {len(df['region'].unique())}")
    lines.append(f"- **Interval**: 30 minutes\n")

    lines.append("### Readings per Region\n")
    for region in REGIONS:
        count = len(df[df['region'] == region])
        lines.append(f"- {region} ({REGION_TO_DC[region]}): {count:,} readings")
    lines.append("")

    # Descriptive stats table
    lines.append("## Descriptive Statistics\n")
    lines.append("| Region | DC | Count | Mean | Median | Std | Min | Max | Q25 | Q75 | CV |")
    lines.append("|--------|-----|-------|------|--------|-----|-----|-----|-----|-----|----|")
    for _, row in desc_stats.iterrows():
        lines.append(
            f"| {row['Region']} | {row['DC']} | {int(row['Count'])} | "
            f"{row['Mean']:.1f} | {row['Median']:.1f} | {row['Std']:.1f} | "
            f"{row['Min']:.0f} | {row['Max']:.0f} | "
            f"{row['Q25']:.1f} | {row['Q75']:.1f} | {row['CV']:.3f} |"
        )
    lines.append("")

    # Week-over-week analysis
    lines.append("## Week-over-Week Analysis\n")
    for region in REGIONS:
        data = week_data[region]
        if data is None:
            lines.append(f"### {region}\n\nInsufficient data for weekly analysis.\n")
            continue
        lines.append(f"### {region}\n")
        lines.append("| Year | Week | Mean CI | Std CI | Slots |")
        lines.append("|------|------|---------|--------|-------|")
        for ws in data['week_summaries']:
            lines.append(
                f"| {ws['year']} | {ws['week']} | {ws['mean']:.1f} | {ws['std']:.1f} | {ws['slots']} |"
            )
        lines.append("")

        # Overall slot variability
        slot_std = data['slot_std']
        if len(slot_std) > 0:
            lines.append(
                f"- Average across-week slot SD: **{slot_std.mean():.1f}** gCO₂/kWh"
            )
            lines.append(
                f"- Max across-week slot SD: **{slot_std.max():.1f}** gCO₂/kWh "
                f"(slot {slot_std.idxmax()})\n"
            )

    # Volatile slots
    lines.append("## Most Volatile Time Slots (Cross-Region)\n")
    lines.append("| Rank | Region | Day | Time | Week-to-Week SD |")
    lines.append("|------|--------|-----|------|-----------------|")
    for rank, v in enumerate(volatile_slots, 1):
        lines.append(f"| {rank} | {v['region']} | {v['day']} | {v['time']} | {v['std']:.1f} |")
    lines.append("")

    # Notable patterns
    lines.append("## Notable Patterns\n")

    # Highest/lowest variability regions
    region_cv = desc_stats.set_index('Region')['CV']
    lines.append(
        f"- **Highest variability**: {region_cv.idxmax()} (CV = {region_cv.max():.3f})"
    )
    lines.append(
        f"- **Lowest variability**: {region_cv.idxmin()} (CV = {region_cv.min():.3f})"
    )

    # Peak CI
    for region in REGIONS:
        rd = df[df['region'] == region]
        peak = rd.loc[rd['actual'].idxmax()]
        lines.append(
            f"- **{region}** peak: {peak['actual']:.0f} gCO₂/kWh at {peak['ts']}"
        )
    lines.append("")

    # Outliers > 3σ
    lines.append("### Outliers (>3σ from region mean)\n")
    outlier_count = 0
    for region in REGIONS:
        rd = df[df['region'] == region]
        mean, std = rd['actual'].mean(), rd['actual'].std()
        outliers = rd[rd['actual'].abs() > mean + 3 * std]
        if len(outliers) > 0:
            lines.append(f"- **{region}**: {len(outliers)} readings above 3σ ({mean + 3*std:.0f} gCO₂/kWh)")
            outlier_count += len(outliers)
    if outlier_count == 0:
        lines.append("- No readings exceed 3σ from their region mean.")
    lines.append("")

    # Graphs
    lines.append("## Visualizations\n")
    lines.append("### Raw 2-Week Comparison\n")
    lines.append("![Raw Comparison](analysis_raw_comparison.png)\n")
    lines.append("### Smoothing Overlays\n")
    lines.append("![Smoothing](analysis_smoothing.png)\n")
    lines.append("### Derivative Signals\n")
    lines.append("![Derivatives](analysis_derivatives.png)\n")
    lines.append("### STL Decomposition\n")
    lines.append("![STL](analysis_stl_decomposition.png)\n")
    lines.append("### Weekly Variance Heatmap\n")
    lines.append("![Heatmap](analysis_weekly_variance.png)\n")

    # Preprocessing observations
    lines.append("## Preprocessing Observations\n")
    lines.append(
        "Based on the analysis above, the following preprocessing strategies may "
        "improve model training:\n"
    )
    lines.append(
        "1. **MA-3h smoothing** reduces high-frequency noise without losing daily "
        "structure — a good candidate for input preprocessing before model training."
    )
    lines.append(
        "2. **diff(48) (day-over-day)** removes the strong diurnal pattern, leaving "
        "residuals that may be easier to model. Consider training on differenced data "
        "and inverting predictions."
    )
    lines.append(
        "3. **STL residuals** show what remains after removing trend and seasonality — "
        "if residuals are small and white-noise-like, the current seasonal features "
        "may already capture most structure."
    )
    lines.append(
        "4. **EWMA-24h** tracks slow regime changes (e.g., weather fronts, "
        "seasonal generation mix shifts). Could serve as an additional feature."
    )
    lines.append(
        "5. **Weekly variance heatmap** reveals which time slots have high "
        "week-to-week variability — model uncertainty estimates should be wider "
        "at these times."
    )
    lines.append("")

    report_path = DOCS_DIR / 'data_analysis.md'
    report_path.write_text('\n'.join(lines))
    print(f"    Saved: {report_path}")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading data...")
    df = load_data()
    print(f"  Loaded {len(df):,} readings across {df['region'].nunique()} regions")
    print(f"  Date range: {df['ts'].min()} to {df['ts'].max()}")

    print("\nComputing descriptive statistics...")
    desc = descriptive_stats(df)
    print(desc.to_string(index=False))

    print("\nComputing week-to-week analysis...")
    week_data = week_analysis(df)

    print("\nFinding most volatile slots...")
    volatile = find_volatile_slots(week_data)
    for v in volatile[:5]:
        print(f"  {v['region']} {v['day']} {v['time']}: SD={v['std']:.1f}")

    print("\nGenerating plots...")
    plot_raw_comparison(df)
    plot_smoothing(df)
    plot_derivatives(df)
    plot_stl(df)
    plot_weekly_variance_heatmap(week_data)

    print("\nGenerating report...")
    generate_report(df, desc, week_data, volatile)

    print("\nDone! All outputs saved to docs/")


if __name__ == '__main__':
    main()

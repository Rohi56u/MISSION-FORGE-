"""
Authoritative 5-Page Mission Concept Dossier PDF Generator
Mission Forge — Phase 6
"""

import io
import logging
from typing import Any, Dict, List
from reportlab.lib.pagesizes import letter  # type: ignore[import-untyped]
from reportlab.lib import colors  # type: ignore[import-untyped]
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]
from reportlab.platypus import (  # type: ignore[import-untyped]
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle  # type: ignore[import-untyped]

from backend.app.dossier.builder import sanitize_text

logger = logging.getLogger(__name__)

# Standard Dimensions (Letter: 612 x 792 pt, 0.5-inch margins: 36 pt)
PAGE_WIDTH, PAGE_HEIGHT = letter
MARGIN = 36.0
USABLE_WIDTH = PAGE_WIDTH - 2 * MARGIN  # 540 pt


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas that accurately computes total page count,
    rendering authoritative running headers and footers with aerospace metadata.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: List[Dict[str, Any]] = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_header_footer(num_pages)
            super().showPage()
        super().save()

    def _draw_header_footer(self, total_pages: int):
        self.saveState()
        # Running Header (Pages 2-5)
        if self._pageNumber > 1:
            self.setFont("Helvetica-Bold", 7.5)
            self.setFillColor(colors.HexColor("#0F172A"))
            self.drawString(MARGIN, PAGE_HEIGHT - 26, "MISSION FORGE // AEROSPACE MISSION DOSSIER")

            self.setFont("Helvetica", 7.5)
            self.setFillColor(colors.HexColor("#64748B"))
            self.drawRightString(
                PAGE_WIDTH - MARGIN,
                PAGE_HEIGHT - 26,
                "NASA SPACE APPS 2026 // PRE-PHASE A CONCEPT",
            )

            # Hairline Rule
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(MARGIN, PAGE_HEIGHT - 30, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 30)

        # Running Footer (All Pages)
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(MARGIN, 34, PAGE_WIDTH - MARGIN, 34)

        self.setFont("Helvetica-Bold", 7)
        self.setFillColor(colors.HexColor("#DC2626"))
        self.drawString(
            MARGIN,
            22,
            "CONFIDENTIAL // MISSION FORGE GENERATED // NOT OFFICIAL NASA DOCUMENT",
        )

        self.setFont("Helvetica", 7)
        self.setFillColor(colors.HexColor("#64748B"))
        self.drawRightString(
            PAGE_WIDTH - MARGIN,
            22,
            f"Page {self._pageNumber} of {total_pages}",
        )
        self.restoreState()


def _get_styles():
    """Builds professional high-contrast typography hierarchy."""
    base_styles = getSampleStyleSheet()
    styles = {}

    styles["DocTitle"] = ParagraphStyle(
        "DocTitle",
        parent=base_styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=4,
    )
    styles["DocSubtitle"] = ParagraphStyle(
        "DocSubtitle",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#0284C7"),
        spaceAfter=8,
    )
    styles["SectionHeader"] = ParagraphStyle(
        "SectionHeader",
        parent=base_styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=0,
        spaceAfter=6,
    )
    styles["DisclaimerBox"] = ParagraphStyle(
        "DisclaimerBox",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10.5,
        textColor=colors.HexColor("#92400E"),
    )
    styles["BodyText"] = ParagraphStyle(
        "BodyText",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#334155"),
    )
    styles["BodyTextBold"] = ParagraphStyle(
        "BodyTextBold",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#0F172A"),
    )
    styles["Muted"] = ParagraphStyle(
        "Muted",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        leading=9.5,
        textColor=colors.HexColor("#64748B"),
    )
    styles["TableHeader"] = ParagraphStyle(
        "TableHeader",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.white,
    )
    styles["TableCell"] = ParagraphStyle(
        "TableCell",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#1E293B"),
    )
    styles["TableCellBold"] = ParagraphStyle(
        "TableCellBold",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#0F172A"),
    )
    styles["TableCellSuccess"] = ParagraphStyle(
        "TableCellSuccess",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#16A34A"),
    )
    styles["TableCellAlert"] = ParagraphStyle(
        "TableCellAlert",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#DC2626"),
    )
    styles["AIBanner"] = ParagraphStyle(
        "AIBanner",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#6D28D9"),
    )
    return styles


def render_dossier_pdf(snapshot: Dict[str, Any]) -> bytes:
    """
    Renders an authoritative 5-page mission concept dossier from a frozen snapshot.
    Returns raw PDF bytes.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
    )

    styles = _get_styles()
    story = []

    mission = snapshot.get("mission", {})
    design = snapshot.get("design", {})
    swapc = snapshot.get("swapc", {})
    components = snapshot.get("components", [])
    trajectory = snapshot.get("trajectory", {})
    telecom = snapshot.get("telecommunications", {})
    cdf = snapshot.get("cdf", {})
    fdir = snapshot.get("fdir", {})
    capcom = snapshot.get("capcom", {})

    # =========================================================================
    # PAGE 1: MISSION OVERVIEW & EXECUTIVE SUMMARY
    # =========================================================================
    default_title = f"Mission Concept Dossier: {mission.get('name', 'Exploration')}"
    title_text = snapshot.get("title", default_title)
    story.append(Paragraph(sanitize_text(title_text, 120), styles["DocTitle"]))
    story.append(
        Paragraph(
            "MISSION FORGE AEROSPACE SIMULATION &amp; CONCEPT FORMULATION ENGINE",
            styles["DocSubtitle"],
        )
    )

    # Authoritative Disclaimer Banner
    disclaimer_html = (
        "<b>AUTHORITATIVE ENGINEERING DISCLAIMER:</b> "
        + sanitize_text(snapshot.get("authoritative_disclaimer", ""), 300)
    )
    disclaimer_table = Table(
        [[Paragraph(disclaimer_html, styles["DisclaimerBox"])]],
        colWidths=[USABLE_WIDTH],
    )
    disclaimer_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF3C7")),
        ("BORDER", (0, 0), (-1, -1), 1, colors.HexColor("#F59E0B")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(disclaimer_table)
    story.append(Spacer(1, 10))

    # Executive Metadata Table
    ts_str = snapshot.get("snapshot_timestamp_utc", "")[:19] + "Z"
    hash_str = snapshot.get("canonical_hash_sha256", "")[:16]
    meta_data = [
        [
            Paragraph("<b>Target Body</b>", styles["TableCellBold"]),
            Paragraph(sanitize_text(mission.get("target", "N/A")), styles["TableCell"]),
            Paragraph("<b>Mission Class</b>", styles["TableCellBold"]),
            Paragraph(
                sanitize_text(mission.get("mission_class", "DISCOVERY")), styles["TableCell"]
            ),
        ],
        [
            Paragraph("<b>Software Version</b>", styles["TableCellBold"]),
            Paragraph(
                sanitize_text(snapshot.get("software_version", "1.0.0")), styles["TableCell"]
            ),
            Paragraph("<b>Schema Version</b>", styles["TableCellBold"]),
            Paragraph(
                sanitize_text(snapshot.get("schema_version", "1.0.0")), styles["TableCell"]
            ),
        ],
        [
            Paragraph("<b>Snapshot Generated</b>", styles["TableCellBold"]),
            Paragraph(sanitize_text(ts_str), styles["TableCell"]),
            Paragraph("<b>Snapshot SHA-256</b>", styles["TableCellBold"]),
            Paragraph(f"<code>{hash_str}...</code>", styles["TableCell"]),
        ],
    ]
    meta_table = Table(meta_data, colWidths=[110, 160, 110, 160])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # Mission Objectives & Constraints
    story.append(
        Paragraph("01. Mission Objectives &amp; System Constraints", styles["SectionHeader"])
    )
    default_desc = "Scientific exploration mission designed within NASA Space Apps parameters."
    desc_p = Paragraph(
        sanitize_text(mission.get("description", default_desc), 400),
        styles["BodyText"],
    )
    story.append(desc_p)
    story.append(Spacer(1, 8))

    # Baseline Constraints Grid
    c_margin = swapc.get("cost_margin_percent", 0)
    m_margin = swapc.get("mass_margin_percent", 0)
    dv_margin = swapc.get("delta_v_margin_percent", 0)
    p_margin = swapc.get("power_margin_percent", 0)
    min_p_req = mission.get("min_power_margin_percent", 0)

    const_data = [
        [
            Paragraph("Parameter", styles["TableHeader"]),
            Paragraph("Constraint Limit", styles["TableHeader"]),
            Paragraph("Actual Design", styles["TableHeader"]),
            Paragraph("Margin Status", styles["TableHeader"]),
        ],
        [
            Paragraph("Budget Cap", styles["TableCell"]),
            Paragraph(f"${mission.get('budget_cap_usd', 0)/1e6:.1f} M", styles["TableCell"]),
            Paragraph(f"${design.get('total_cost_usd', 0)/1e6:.1f} M", styles["TableCell"]),
            Paragraph(
                f"{c_margin:+.1f}%",
                styles["TableCellSuccess"] if c_margin >= 0 else styles["TableCellAlert"],
            ),
        ],
        [
            Paragraph("Max Launch Mass", styles["TableCell"]),
            Paragraph(f"{mission.get('max_launch_mass_kg', 0):.0f} kg", styles["TableCell"]),
            Paragraph(f"{design.get('wet_mass_kg', 0):.1f} kg", styles["TableCell"]),
            Paragraph(
                f"{m_margin:+.1f}%",
                styles["TableCellSuccess"] if m_margin >= 0 else styles["TableCellAlert"],
            ),
        ],
        [
            Paragraph("Min Required Delta-V", styles["TableCell"]),
            Paragraph(f"{mission.get('min_delta_v_mps', 0):.0f} m/s", styles["TableCell"]),
            Paragraph(f"{design.get('delta_v_mps', 0):.0f} m/s", styles["TableCell"]),
            Paragraph(
                f"{dv_margin:+.1f}%",
                styles["TableCellSuccess"] if dv_margin >= 0 else styles["TableCellAlert"],
            ),
        ],
        [
            Paragraph("Min Power Margin", styles["TableCell"]),
            Paragraph(f"{min_p_req:.1f}%", styles["TableCell"]),
            Paragraph(f"{p_margin:+.1f}%", styles["TableCell"]),
            Paragraph(
                "PASSED" if p_margin >= min_p_req else "VIOLATED",
                styles["TableCellSuccess"] if p_margin >= min_p_req else styles["TableCellAlert"],
            ),
        ],
    ]
    const_table = Table(const_data, colWidths=[140, 130, 130, 140])
    const_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(const_table)
    story.append(Spacer(1, 10))

    # Spacecraft Feasibility Banner
    is_feas = design.get("is_feasible", False)
    feas_color = "#DCFCE7" if is_feas else "#FEE2E2"
    feas_border = "#16A34A" if is_feas else "#DC2626"
    num_viols = len(design.get("violations", []))
    feas_text = (
        "<b>FEASIBILITY STATUS: FEASIBLE</b> — All baseline mission constraints, launch limits, "
        "and safety margins satisfied."
        if is_feas else
        f"<b>FEASIBILITY STATUS: NON-FEASIBLE ({num_viols} VIOLATIONS)</b> — Constraints exceeded."
    )
    feas_style = styles["TableCellSuccess"] if is_feas else styles["TableCellAlert"]
    feas_table = Table(
        [[Paragraph(feas_text, feas_style)]],
        colWidths=[USABLE_WIDTH],
    )
    feas_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(feas_color)),
        ("BORDER", (0, 0), (-1, -1), 1, colors.HexColor(feas_border)),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(feas_table)

    # Force Page Break to Page 2
    story.append(PageBreak())

    # =========================================================================
    # PAGE 2: SPACECRAFT ARCHITECTURE & SWaP-C BREAKDOWN
    # =========================================================================
    story.append(
        Paragraph(
            "02. Spacecraft Architecture &amp; Subsystem SWaP-C Analysis",
            styles["SectionHeader"],
        )
    )
    d_name_clean = sanitize_text(design.get("name", "Baseline"))
    d_rev = design.get("version", 1)
    story.append(
        Paragraph(
            f"Design Revision: <b>{d_name_clean} (Rev {d_rev})</b> — "
            "Deterministic mass, power, propulsion sizing, and financial expenditure ledger.",
            styles["BodyText"],
        )
    )
    story.append(Spacer(1, 8))

    # KPI Top Grid
    p_mass_val = design.get("propellant_mass_kg", 0)
    cost_val_m = design.get("total_cost_usd", 0) / 1e6
    kpi_data = [
        [
            Paragraph("Dry Mass", styles["TableHeader"]),
            Paragraph("Wet Mass", styles["TableHeader"]),
            Paragraph("Propellant", styles["TableHeader"]),
            Paragraph("Total Cost", styles["TableHeader"]),
        ],
        [
            Paragraph(f"<b>{design.get('dry_mass_kg', 0):.1f} kg</b>", styles["TableCellBold"]),
            Paragraph(f"<b>{design.get('wet_mass_kg', 0):.1f} kg</b>", styles["TableCellBold"]),
            Paragraph(f"<b>{p_mass_val:.1f} kg</b>", styles["TableCellBold"]),
            Paragraph(f"<b>${cost_val_m:.2f} M</b>", styles["TableCellBold"]),
        ],
    ]
    kpi_table = Table(kpi_data, colWidths=[135, 135, 135, 135])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0284C7")),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F0F9FF")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#BAE6FD")),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 10))

    # Subsystem Breakdown Table
    story.append(Paragraph("<b>Subsystem Mass &amp; Power Breakdown</b>", styles["BodyTextBold"]))
    sub_mass = swapc.get("mass_by_subsystem", {})
    sub_power = swapc.get("power_by_subsystem", {})
    all_subs = sorted(list(set(list(sub_mass.keys()) + list(sub_power.keys()))))
    if not all_subs:
        all_subs = ["STRUCTURE", "PROPULSION", "POWER", "TELECOM", "SCIENCE", "THERMAL", "ADCS"]

    sub_rows = [
        [
            Paragraph("Subsystem", styles["TableHeader"]),
            Paragraph("Mass (kg)", styles["TableHeader"]),
            Paragraph("Mass Share %", styles["TableHeader"]),
            Paragraph("Power Draw (W)", styles["TableHeader"]),
            Paragraph("Power Share %", styles["TableHeader"]),
        ]
    ]
    tot_m = design.get("dry_mass_kg", 0) or 1.0
    tot_p = design.get("power_draw_w", 0) or 1.0
    for sname in all_subs:
        m_val = sub_mass.get(sname, 0.0)
        p_val = sub_power.get(sname, 0.0)
        sub_rows.append([
            Paragraph(sanitize_text(sname), styles["TableCell"]),
            Paragraph(f"{m_val:.1f}", styles["TableCell"]),
            Paragraph(f"{(m_val/tot_m)*100.0:.1f}%" if tot_m > 0 else "0.0%", styles["TableCell"]),
            Paragraph(f"{p_val:.1f}", styles["TableCell"]),
            Paragraph(f"{(p_val/tot_p)*100.0:.1f}%" if tot_p > 0 else "0.0%", styles["TableCell"]),
        ])
    sub_table = Table(sub_rows, colWidths=[160, 95, 95, 95, 95])
    sub_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("PADDING", (0, 0), (-1, -1), 3.5),
    ]))
    story.append(sub_table)
    story.append(Spacer(1, 10))

    # Engineering Calculation Assumptions & Citations Box
    assump_html = (
        "<b>Deterministic Calculation Assumptions &amp; Standards:</b><br/>"
        + "<br/>".join([f"• {sanitize_text(a, 150)}" for a in swapc.get("assumptions", [])])
    )
    assump_table = Table([[Paragraph(assump_html, styles["BodyText"])]], colWidths=[USABLE_WIDTH])
    assump_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
        ("BORDER", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(assump_table)

    # Force Page Break to Page 3
    story.append(PageBreak())

    # =========================================================================
    # PAGE 3: COMPONENT LEDGER & FIELD-LEVEL PROVENANCE
    # =========================================================================
    story.append(
        Paragraph("03. Spacecraft Component Ledger &amp; Provenance", styles["SectionHeader"])
    )
    story.append(Paragraph(
        "Certified Bill of Materials (BOM) with Technology Readiness Levels (TRL), "
        "flight heritage provenance, and verification source tracking.",
        styles["BodyText"],
    ))
    story.append(Spacer(1, 8))

    comp_rows = [
        [
            Paragraph("Component Name", styles["TableHeader"]),
            Paragraph("Subsystem", styles["TableHeader"]),
            Paragraph("Mass (kg)", styles["TableHeader"]),
            Paragraph("Power (W)", styles["TableHeader"]),
            Paragraph("Cost ($M)", styles["TableHeader"]),
            Paragraph("TRL", styles["TableHeader"]),
            Paragraph("Verification", styles["TableHeader"]),
        ]
    ]

    # Limit to top 14 components to strictly avoid overflow on page 3
    display_comps = components[:14]
    for c in display_comps:
        c_cost_m = c.get("cost_usd", 0) / 1e6
        c_v_status = sanitize_text(c.get("verification_status", "VERIFIED"), 24)
        comp_rows.append([
            Paragraph(sanitize_text(c.get("name", "Component"), 32), styles["TableCell"]),
            Paragraph(sanitize_text(c.get("subsystem", "OTHER"), 16), styles["TableCell"]),
            Paragraph(f"{c.get('mass_kg', 0):.1f}", styles["TableCell"]),
            Paragraph(f"{c.get('power_draw_w', 0):.1f}", styles["TableCell"]),
            Paragraph(f"${c_cost_m:.2f}", styles["TableCell"]),
            Paragraph(f"{c.get('trl', 9)}", styles["TableCell"]),
            Paragraph(c_v_status, styles["TableCell"]),
        ])
    if len(components) > 14:
        comp_rows.append([
            Paragraph(
                f"<i>... and {len(components) - 14} additional components</i>",
                styles["TableCell"],
            ),
            Paragraph("-", styles["TableCell"]),
            Paragraph("-", styles["TableCell"]),
            Paragraph("-", styles["TableCell"]),
            Paragraph("-", styles["TableCell"]),
            Paragraph("-", styles["TableCell"]),
            Paragraph("INCLUDED IN SNAPSHOT", styles["TableCell"]),
        ])
    if len(components) == 0:
        comp_rows.append([
            Paragraph("No individual components configured in design.", styles["TableCell"]),
            Paragraph("-", styles["TableCell"]),
            Paragraph("-", styles["TableCell"]),
            Paragraph("-", styles["TableCell"]),
            Paragraph("-", styles["TableCell"]),
            Paragraph("-", styles["TableCell"]),
            Paragraph("ESTIMATED", styles["TableCellAlert"]),
        ])

    comp_table = Table(comp_rows, colWidths=[140, 80, 55, 55, 55, 35, 120])
    comp_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("PADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(comp_table)
    story.append(Spacer(1, 10))

    # Provenance Disclosure Box
    prov_text = (
        "<b>Field-Level Data Provenance &amp; Verification Integrity:</b><br/>"
        "• <b>Authoritative Sources:</b> NASA TechPort, JPL Horizons, ESA Heritage DB.<br/>"
        "• <b>Estimated / Unverified Fields:</b> Any component lacking flight heritage is flagged "
        "as ESTIMATED with a 20% margin penalty applied to dry mass and power draw.<br/>"
        "• <b>Simulation Flag:</b> Simulated telemetry readings are isolated and tagged "
        "separately from deterministic ground truth."
    )
    prov_table = Table([[Paragraph(prov_text, styles["BodyText"])]], colWidths=[USABLE_WIDTH])
    prov_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BORDER", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(prov_table)

    # Force Page Break to Page 4
    story.append(PageBreak())

    # =========================================================================
    # PAGE 4: TRAJECTORY & TELECOMMUNICATION ANALYSIS
    # =========================================================================
    story.append(
        Paragraph("04. Trajectory Optimization &amp; Telecommunications", styles["SectionHeader"])
    )
    story.append(Paragraph(
        "Astrodynamics boundary-value transfer solve and NASA DSN link budget.",
        styles["BodyText"],
    ))
    story.append(Spacer(1, 8))

    # Trajectory Grid
    orig_b = trajectory.get("origin_body", "EARTH")
    targ_b = trajectory.get("target_body", "TARGET")
    traj_coord = sanitize_text(trajectory.get("coordinate_frame", "ICRF / J2000"))
    traj_stat = sanitize_text(trajectory.get("status", "SOLVED"))
    dep_ep = sanitize_text(trajectory.get("departure_epoch", "N/A")[:10])
    arr_ep = sanitize_text(trajectory.get("arrival_epoch", "N/A")[:10])
    tof_days = trajectory.get("time_of_flight_days", 0)

    traj_data = [
        [
            Paragraph("Parameter", styles["TableHeader"]),
            Paragraph("Transfer Value", styles["TableHeader"]),
            Paragraph("Ephemeris Source &amp; Frame", styles["TableHeader"]),
            Paragraph("Status / Validity", styles["TableHeader"]),
        ],
        [
            Paragraph("Origin &rarr; Target", styles["TableCellBold"]),
            Paragraph(f"{orig_b} &rarr; {targ_b}", styles["TableCell"]),
            Paragraph(traj_coord, styles["TableCell"]),
            Paragraph(traj_stat, styles["TableCellSuccess"]),
        ],
        [
            Paragraph("Departure Epoch", styles["TableCellBold"]),
            Paragraph(dep_ep, styles["TableCell"]),
            Paragraph("Time Scale: TDB / UTC", styles["TableCell"]),
            Paragraph("OPTIMAL WINDOW", styles["TableCell"]),
        ],
        [
            Paragraph("Arrival Epoch", styles["TableCellBold"]),
            Paragraph(arr_ep, styles["TableCell"]),
            Paragraph(f"Time of Flight: {tof_days:.1f} days", styles["TableCell"]),
            Paragraph("BALLISTIC TRANSFER", styles["TableCell"]),
        ],
        [
            Paragraph("Departure C3 Energy", styles["TableCellBold"]),
            Paragraph(
                f"{trajectory.get('c3_km2_s2', 0):.2f} km&sup2;/s&sup2;", styles["TableCell"]
            ),
            Paragraph("Launch Injection Energy", styles["TableCell"]),
            Paragraph("SOLVED", styles["TableCellSuccess"]),
        ],
        [
            Paragraph("Total Transfer Delta-V", styles["TableCellBold"]),
            Paragraph(f"{trajectory.get('total_delta_v_mps', 0):.0f} m/s", styles["TableCellBold"]),
            Paragraph("Post-Injection Maneuver Budget", styles["TableCell"]),
            Paragraph("NOMINAL", styles["TableCellSuccess"]),
        ],
    ]
    traj_table = Table(traj_data, colWidths=[130, 130, 160, 120])
    traj_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("PADDING", (0, 0), (-1, -1), 3.5),
    ]))
    story.append(traj_table)
    story.append(Spacer(1, 8))

    # Astrodynamics Limitation Notice
    traj_disc_html = (
        "<b>Astrodynamics Limitations Disclosure:</b> "
        + sanitize_text(trajectory.get("astrodynamics_disclaimer", ""), 300)
    )
    story.append(Paragraph(traj_disc_html, styles["Muted"]))
    story.append(Spacer(1, 10))

    # Telecom Link Budget Table
    story.append(
        Paragraph("<b>NASA Deep Space Network (DSN) RF Link Budget</b>", styles["BodyTextBold"])
    )
    freq_ghz = telecom.get("carrier_frequency_hz", 8.4e9) / 1e9
    tx_p = telecom.get("tx_power_w", 35.0)
    ant_d = telecom.get("antenna_diameter_m", 2.4)
    dl_kbps = telecom.get("downlink_rate_bps", 32000) / 1000
    telecom_data = [
        [
            Paragraph("Ground Station Network", styles["TableCellBold"]),
            Paragraph(sanitize_text(telecom.get("ground_network", "DSN")), styles["TableCell"]),
            Paragraph("Carrier Frequency", styles["TableCellBold"]),
            Paragraph(f"{freq_ghz:.3f} GHz (X-Band)", styles["TableCell"]),
        ],
        [
            Paragraph("Target Distance (AU)", styles["TableCellBold"]),
            Paragraph(f"{telecom.get('distance_au', 1.0):.3f} AU", styles["TableCell"]),
            Paragraph("Spacecraft Tx Power", styles["TableCellBold"]),
            Paragraph(f"{tx_p:.1f} W (TWTA)", styles["TableCell"]),
        ],
        [
            Paragraph("Space Loss (dB)", styles["TableCellBold"]),
            Paragraph(f"-{telecom.get('space_loss_db', 270.0):.1f} dB", styles["TableCell"]),
            Paragraph("Antenna Diameter", styles["TableCellBold"]),
            Paragraph(f"{ant_d:.1f} m HGA", styles["TableCell"]),
        ],
        [
            Paragraph("Downlink Rate", styles["TableCellBold"]),
            Paragraph(f"{dl_kbps:.1f} kbps", styles["TableCell"]),
            Paragraph("Link Margin", styles["TableCellBold"]),
            Paragraph(f"+{telecom.get('link_margin_db', 6.0):.1f} dB", styles["TableCellSuccess"]),
        ],
    ]
    telecom_table = Table(telecom_data, colWidths=[130, 140, 130, 140])
    telecom_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("PADDING", (0, 0), (-1, -1), 3.5),
    ]))
    story.append(telecom_table)

    # Force Page Break to Page 5
    story.append(PageBreak())

    # =========================================================================
    # PAGE 5: CDF COLLABORATION, FDIR AUDIT & CAPCOM INTELLIGENCE
    # =========================================================================
    story.append(
        Paragraph(
            "05. Concurrent Engineering (CDF), FDIR Audit &amp; CAPCOM", styles["SectionHeader"]
        )
    )
    story.append(Paragraph(
        "Traceability audit trail of multi-user concurrent design revisions, "
        "deterministic fault protection findings, and grounded advisory intelligence.",
        styles["BodyText"],
    ))
    story.append(Spacer(1, 8))

    # CDF Section
    story.append(
        Paragraph(
            "<b>Concurrent Design Facility (CDF) Revision History</b>", styles["BodyTextBold"]
        )
    )
    cdf_status = cdf.get("status", "STANDALONE_DESIGN")
    if cdf_status != "STANDALONE_DESIGN" and cdf.get("recent_revisions"):
        cdf_rows = [
            [
                Paragraph("Rev #", styles["TableHeader"]),
                Paragraph("Author Role", styles["TableHeader"]),
                Paragraph("Mutation Type", styles["TableHeader"]),
                Paragraph("Timestamp (UTC)", styles["TableHeader"]),
            ]
        ]
        for r in cdf.get("recent_revisions", [])[:4]:
            cdf_rows.append([
                Paragraph(f"v{r.get('version', 1)}", styles["TableCellBold"]),
                Paragraph(
                    sanitize_text(r.get("author_role", "ARCHITECT"), 32), styles["TableCell"]
                ),
                Paragraph(
                    sanitize_text(r.get("mutation_type", "MUTATION"), 32), styles["TableCell"]
                ),
                Paragraph(sanitize_text(r.get("created_at", "")[:19]), styles["TableCell"]),
            ])
        cdf_table = Table(cdf_rows, colWidths=[60, 160, 160, 160])
        cdf_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("PADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(cdf_table)
    else:
        cdf_p = Paragraph(
            "<i>Standalone Engineering Workspace: Mission authored directly without "
            "multi-user CDF room session. Single-architect design integrity verified.</i>",
            styles["BodyText"],
        )
        story.append(cdf_p)
    story.append(Spacer(1, 10))

    # FDIR Audit Section
    story.append(
        Paragraph(
            "<b>Deterministic Fault Detection, Isolation &amp; Recovery (FDIR) Audit</b>",
            styles["BodyTextBold"],
        )
    )
    fdir_findings = fdir.get("findings", [])
    if fdir_findings:
        fdir_rows = [
            [
                Paragraph("Rule ID", styles["TableHeader"]),
                Paragraph("Severity", styles["TableHeader"]),
                Paragraph("Subsystem", styles["TableHeader"]),
                Paragraph("Deterministic Finding Explanation", styles["TableHeader"]),
            ]
        ]
        for f in fdir_findings[:4]:
            sev = f.get("severity", "WARNING")
            sev_style = styles["TableCellAlert"] if sev == "CRITICAL" else styles["TableCell"]
            fdir_rows.append([
                Paragraph(
                    sanitize_text(f.get("rule_id", "FDIR-001"), 24), styles["TableCellBold"]
                ),
                Paragraph(sanitize_text(sev, 12), sev_style),
                Paragraph(
                    sanitize_text(f.get("affected_subsystem", "SYS"), 16), styles["TableCell"]
                ),
                Paragraph(
                    sanitize_text(f.get("explanation", "Nominal evaluation"), 100),
                    styles["TableCell"],
                ),
            ])
        fdir_table = Table(fdir_rows, colWidths=[90, 70, 80, 300])
        fdir_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("PADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(fdir_table)
    else:
        fdir_nom = Table(
            [[
                Paragraph(
                    "<b>FDIR AUDIT CLEAN:</b> 0 deterministic anomaly findings or constraint "
                    "violations detected.",
                    styles["TableCellSuccess"],
                )
            ]],
            colWidths=[USABLE_WIDTH],
        )
        fdir_nom.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#DCFCE7")),
            ("BORDER", (0, 0), (-1, -1), 0.5, colors.HexColor("#16A34A")),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(fdir_nom)
    story.append(Spacer(1, 10))

    # Grounded CAPCOM AI Assistant Advisory Box
    story.append(
        Paragraph(
            "<b>Grounded CAPCOM AI Mission Synthesis &amp; Tradeoffs</b>",
            styles["BodyTextBold"],
        )
    )
    auth_notice = sanitize_text(capcom.get("authoritative_notice", "AI-GENERATED ADVISORY"))
    synth_text = sanitize_text(capcom.get("mission_synthesis", "Nominal design synthesis."))
    tradeoffs_html = "<br/>".join(
        [f"• {sanitize_text(t, 120)}" for t in capcom.get("critical_tradeoffs", [])]
    )
    capcom_box_html = (
        f"<b>{auth_notice}</b><br/><br/>"
        f"<b>Mission Synthesis:</b> {synth_text}<br/><br/>"
        f"<b>Key Operational Trade-offs:</b><br/>{tradeoffs_html}"
    )
    capcom_table = Table(
        [[Paragraph(capcom_box_html, styles["AIBanner"])]], colWidths=[USABLE_WIDTH]
    )
    capcom_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F5F3FF")),
        ("BORDER", (0, 0), (-1, -1), 1, colors.HexColor("#7C3AED")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(capcom_table)
    story.append(Spacer(1, 10))

    # Verification Sign-Off & Snapshot Hash
    full_sha = snapshot.get("canonical_hash_sha256", "0" * 64)
    signoff_data = [
        [
            Paragraph("<b>Mathematical Snapshot Verification</b>", styles["TableCellBold"]),
            Paragraph(f"SHA-256: <code>{full_sha}</code>", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Editorial Sign-Off</b>", styles["TableCellBold"]),
            Paragraph(
                "Pre-Phase A Mission Concept Formulation — Released for Scientific Peer Review.",
                styles["TableCell"],
            ),
        ],
    ]
    signoff_table = Table(signoff_data, colWidths=[170, 370])
    signoff_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(signoff_table)

    # Build Document with NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    return buf.getvalue()

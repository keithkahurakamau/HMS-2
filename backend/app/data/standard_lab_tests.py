"""Standard laboratory test catalogue.

A comprehensive, curated list of the lab tests a general hospital offers,
used to preload every tenant's lab catalogue (and, via the price-list sync,
the billing price list). Idempotent seeding keys on the test name, so
hospitals can freely rename prices, deactivate tests they don't offer, and
add their own — re-seeding never overwrites local changes.

Prices are sensible KES defaults for a mid-tier Kenyan facility; every
hospital is expected to tune them in Accounting → Price List.

Shape: (test_name, category, default_specimen_type, base_price_kes, turnaround_hours)
"""

STANDARD_LAB_TESTS: list[tuple[str, str, str, int, int]] = [
    # ── Hematology ──────────────────────────────────────────────────────────
    ("Full Blood Count (CBC)",                  "Hematology", "Whole Blood", 500,  4),
    ("Hemoglobin (Hb)",                         "Hematology", "Whole Blood", 200,  2),
    ("Peripheral Blood Film",                   "Hematology", "Whole Blood", 600,  24),
    ("Erythrocyte Sedimentation Rate (ESR)",    "Hematology", "Whole Blood", 300,  4),
    ("Reticulocyte Count",                      "Hematology", "Whole Blood", 600,  24),
    ("Sickling Test",                           "Hematology", "Whole Blood", 400,  4),
    ("Hemoglobin Electrophoresis",              "Hematology", "Whole Blood", 2500, 72),
    ("G6PD Screen",                             "Hematology", "Whole Blood", 1200, 24),
    ("Malaria Parasites (Blood Slide)",         "Parasitology", "Whole Blood", 300, 2),
    ("Malaria Rapid Diagnostic Test (mRDT)",    "Parasitology", "Whole Blood", 400, 1),
    ("Bone Marrow Aspirate Examination",        "Hematology", "Bone Marrow", 6000, 96),

    # ── Coagulation ─────────────────────────────────────────────────────────
    ("Prothrombin Time / INR (PT/INR)",         "Coagulation", "Plasma", 1000, 4),
    ("Activated Partial Thromboplastin Time (APTT)", "Coagulation", "Plasma", 1200, 4),
    ("D-Dimer",                                 "Coagulation", "Plasma", 2500, 6),
    ("Fibrinogen",                              "Coagulation", "Plasma", 1800, 24),
    ("Bleeding Time",                           "Coagulation", "Whole Blood", 500, 2),

    # ── Blood bank / transfusion ────────────────────────────────────────────
    ("Blood Group & Rhesus (ABO/Rh)",           "Blood Bank", "Whole Blood", 300, 2),
    ("Direct Coombs Test",                      "Blood Bank", "Whole Blood", 900, 24),
    ("Indirect Coombs Test",                    "Blood Bank", "Serum", 900, 24),
    ("Cross-match (per unit)",                  "Blood Bank", "Whole Blood", 1200, 4),

    # ── Clinical chemistry: renal / electrolytes ────────────────────────────
    ("Urea, Electrolytes & Creatinine (UEC)",   "Clinical Chemistry", "Serum", 1200, 6),
    ("Creatinine",                              "Clinical Chemistry", "Serum", 400, 4),
    ("Urea (BUN)",                              "Clinical Chemistry", "Serum", 400, 4),
    ("Sodium / Potassium / Chloride",           "Clinical Chemistry", "Serum", 800, 4),
    ("Estimated GFR (eGFR)",                    "Clinical Chemistry", "Serum", 500, 6),
    ("Uric Acid",                               "Clinical Chemistry", "Serum", 500, 6),
    ("Calcium (Total)",                         "Clinical Chemistry", "Serum", 500, 6),
    ("Phosphate",                               "Clinical Chemistry", "Serum", 500, 6),
    ("Magnesium",                               "Clinical Chemistry", "Serum", 600, 6),

    # ── Clinical chemistry: liver ───────────────────────────────────────────
    ("Liver Function Tests (LFTs)",             "Clinical Chemistry", "Serum", 1500, 6),
    ("ALT (SGPT)",                              "Clinical Chemistry", "Serum", 400, 4),
    ("AST (SGOT)",                              "Clinical Chemistry", "Serum", 400, 4),
    ("Alkaline Phosphatase (ALP)",              "Clinical Chemistry", "Serum", 400, 4),
    ("Gamma-GT (GGT)",                          "Clinical Chemistry", "Serum", 500, 6),
    ("Total / Direct Bilirubin",                "Clinical Chemistry", "Serum", 500, 4),
    ("Total Protein",                           "Clinical Chemistry", "Serum", 400, 6),
    ("Albumin",                                 "Clinical Chemistry", "Serum", 400, 6),
    ("Ammonia",                                 "Clinical Chemistry", "Plasma", 2000, 6),

    # ── Clinical chemistry: glucose / diabetes ──────────────────────────────
    ("Random Blood Sugar (RBS)",                "Clinical Chemistry", "Whole Blood", 200, 1),
    ("Fasting Blood Sugar (FBS)",               "Clinical Chemistry", "Whole Blood", 250, 2),
    ("Oral Glucose Tolerance Test (OGTT)",      "Clinical Chemistry", "Whole Blood", 900, 4),
    ("Glycated Hemoglobin (HbA1c)",             "Clinical Chemistry", "Whole Blood", 1500, 6),

    # ── Clinical chemistry: lipids / cardiac / pancreas ─────────────────────
    ("Lipid Profile",                           "Clinical Chemistry", "Serum", 1500, 6),
    ("Total Cholesterol",                       "Clinical Chemistry", "Serum", 500, 4),
    ("Triglycerides",                           "Clinical Chemistry", "Serum", 500, 4),
    ("HDL / LDL Cholesterol",                   "Clinical Chemistry", "Serum", 800, 6),
    ("Troponin I/T (Cardiac)",                  "Clinical Chemistry", "Serum", 2500, 2),
    ("CK-MB",                                   "Clinical Chemistry", "Serum", 1500, 4),
    ("Creatine Kinase (Total CK)",              "Clinical Chemistry", "Serum", 1200, 6),
    ("Lactate Dehydrogenase (LDH)",             "Clinical Chemistry", "Serum", 800, 6),
    ("BNP / NT-proBNP",                         "Clinical Chemistry", "Plasma", 4000, 6),
    ("Amylase",                                 "Clinical Chemistry", "Serum", 900, 4),
    ("Lipase",                                  "Clinical Chemistry", "Serum", 1200, 4),

    # ── Inflammation / sepsis ───────────────────────────────────────────────
    ("C-Reactive Protein (CRP)",                "Immunology", "Serum", 900, 4),
    ("Procalcitonin",                           "Immunology", "Serum", 3500, 6),
    ("Ferritin",                                "Clinical Chemistry", "Serum", 1500, 6),
    ("Serum Iron / TIBC",                       "Clinical Chemistry", "Serum", 1800, 24),
    ("Vitamin B12",                             "Clinical Chemistry", "Serum", 2000, 24),
    ("Folate",                                  "Clinical Chemistry", "Serum", 2000, 24),
    ("Vitamin D (25-OH)",                       "Clinical Chemistry", "Serum", 3500, 24),
    ("Blood Lactate",                           "Clinical Chemistry", "Whole Blood", 1200, 2),
    ("Arterial Blood Gas (ABG)",                "Clinical Chemistry", "Arterial Blood", 2500, 1),

    # ── Endocrinology / hormones ────────────────────────────────────────────
    ("Thyroid Function Tests (TSH, T3, T4)",    "Endocrinology", "Serum", 2500, 24),
    ("TSH",                                     "Endocrinology", "Serum", 1200, 24),
    ("Free T4",                                 "Endocrinology", "Serum", 1200, 24),
    ("Free T3",                                 "Endocrinology", "Serum", 1200, 24),
    ("Prolactin",                               "Endocrinology", "Serum", 1500, 24),
    ("Cortisol (AM)",                           "Endocrinology", "Serum", 2000, 24),
    ("FSH",                                     "Endocrinology", "Serum", 1500, 24),
    ("LH",                                      "Endocrinology", "Serum", 1500, 24),
    ("Estradiol (E2)",                          "Endocrinology", "Serum", 1800, 24),
    ("Progesterone",                            "Endocrinology", "Serum", 1800, 24),
    ("Testosterone (Total)",                    "Endocrinology", "Serum", 1800, 24),
    ("Beta-hCG (Quantitative)",                 "Endocrinology", "Serum", 1500, 6),
    ("Insulin (Fasting)",                       "Endocrinology", "Serum", 2500, 24),
    ("Parathyroid Hormone (PTH)",               "Endocrinology", "Serum", 3000, 48),

    # ── Tumor markers ───────────────────────────────────────────────────────
    ("PSA (Total)",                             "Tumor Markers", "Serum", 1800, 24),
    ("CEA",                                     "Tumor Markers", "Serum", 2000, 24),
    ("CA 125",                                  "Tumor Markers", "Serum", 2500, 24),
    ("CA 19-9",                                 "Tumor Markers", "Serum", 2500, 24),
    ("CA 15-3",                                 "Tumor Markers", "Serum", 2500, 24),
    ("Alpha-Fetoprotein (AFP)",                 "Tumor Markers", "Serum", 2000, 24),

    # ── Serology / immunology / infectious ──────────────────────────────────
    ("HIV Antibody Test (Rapid)",               "Serology", "Whole Blood", 0, 1),
    ("HIV Viral Load",                          "Molecular", "Plasma", 4500, 96),
    ("CD4 Count",                               "Immunology", "Whole Blood", 1500, 24),
    ("Hepatitis B Surface Antigen (HBsAg)",     "Serology", "Serum", 800, 4),
    ("Hepatitis B Profile (Panel)",             "Serology", "Serum", 3500, 48),
    ("Hepatitis C Antibody (Anti-HCV)",         "Serology", "Serum", 1200, 24),
    ("Hepatitis A IgM",                         "Serology", "Serum", 1800, 48),
    ("VDRL / RPR (Syphilis)",                   "Serology", "Serum", 500, 4),
    ("TPHA (Syphilis Confirmatory)",            "Serology", "Serum", 1000, 24),
    ("Widal Test (Typhoid)",                    "Serology", "Serum", 500, 4),
    ("Brucella Agglutination Test",             "Serology", "Serum", 800, 24),
    ("H. pylori Antigen (Stool)",               "Serology", "Stool", 1200, 6),
    ("H. pylori Antibody",                      "Serology", "Serum", 1000, 6),
    ("Rheumatoid Factor (RF)",                  "Immunology", "Serum", 900, 24),
    ("Anti-CCP",                                "Immunology", "Serum", 3000, 48),
    ("Antinuclear Antibody (ANA)",              "Immunology", "Serum", 2500, 72),
    ("ASO Titre",                               "Serology", "Serum", 800, 24),
    ("Dengue NS1 / IgM",                        "Serology", "Serum", 2000, 6),
    ("COVID-19 Antigen (Rapid)",                "Serology", "Nasopharyngeal Swab", 1000, 1),
    ("COVID-19 PCR",                            "Molecular", "Nasopharyngeal Swab", 4500, 24),
    ("TB GeneXpert (MTB/RIF)",                  "Molecular", "Sputum", 0, 24),
    ("Cryptococcal Antigen (CrAg)",             "Serology", "Serum", 1500, 6),
    ("Toxoplasma IgG/IgM",                      "Serology", "Serum", 2200, 48),
    ("Rubella IgG/IgM",                         "Serology", "Serum", 2200, 48),
    ("CMV IgG/IgM",                             "Serology", "Serum", 2500, 48),

    # ── Microbiology / cultures ─────────────────────────────────────────────
    ("Blood Culture & Sensitivity",             "Microbiology", "Whole Blood", 2500, 96),
    ("Urine Culture & Sensitivity",             "Microbiology", "Urine", 1500, 72),
    ("Stool Culture & Sensitivity",             "Microbiology", "Stool", 1500, 72),
    ("Sputum Culture & Sensitivity",            "Microbiology", "Sputum", 1500, 72),
    ("Wound Swab Culture & Sensitivity",        "Microbiology", "Swab", 1500, 72),
    ("Throat Swab Culture",                     "Microbiology", "Swab", 1200, 72),
    ("High Vaginal Swab (HVS) M/C/S",           "Microbiology", "Swab", 1200, 72),
    ("Urethral Swab M/C/S",                     "Microbiology", "Swab", 1200, 72),
    ("CSF Analysis (Biochem + Micro)",          "Microbiology", "CSF", 3000, 24),
    ("Gram Stain",                              "Microbiology", "Swab", 500, 4),
    ("ZN Stain (AFB) for TB",                   "Microbiology", "Sputum", 500, 24),
    ("KOH Preparation (Fungal)",                "Microbiology", "Skin Scraping", 500, 4),
    ("Semen Analysis",                          "Microbiology", "Semen", 1500, 24),

    # ── Urinalysis / stool ──────────────────────────────────────────────────
    ("Urinalysis (Dipstick + Microscopy)",      "Urinalysis", "Urine", 300, 2),
    ("Urine Pregnancy Test (UPT)",              "Urinalysis", "Urine", 200, 1),
    ("24-Hour Urine Protein",                   "Urinalysis", "Urine", 1500, 48),
    ("Urine Microalbumin (ACR)",                "Urinalysis", "Urine", 1200, 24),
    ("Urine Drugs of Abuse Screen",             "Urinalysis", "Urine", 2500, 6),
    ("Stool Microscopy (Ova & Cysts)",          "Parasitology", "Stool", 300, 4),
    ("Stool Occult Blood",                      "Parasitology", "Stool", 500, 6),

    # ── Histology / cytology ────────────────────────────────────────────────
    ("Pap Smear (Cervical Cytology)",           "Cytology", "Cervical Smear", 1500, 120),
    ("Fine Needle Aspiration Cytology (FNAC)",  "Cytology", "Tissue Aspirate", 3500, 120),
    ("Histology (Small Biopsy)",                "Histology", "Tissue", 4500, 168),
    ("Histology (Large Specimen)",              "Histology", "Tissue", 7000, 168),

    # ── Therapeutic drug monitoring / misc ──────────────────────────────────
    ("Digoxin Level",                           "Clinical Chemistry", "Serum", 2500, 24),
    ("Phenytoin Level",                         "Clinical Chemistry", "Serum", 2500, 24),
    ("Valproate Level",                         "Clinical Chemistry", "Serum", 2500, 24),
    ("Lithium Level",                           "Clinical Chemistry", "Serum", 2500, 24),
    ("Alcohol (Ethanol) Level",                 "Clinical Chemistry", "Serum", 2000, 6),
]

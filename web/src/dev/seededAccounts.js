// Directory of the demo accounts created by scripts/setup.sh's seed step.
// This is convenience data for the dev-only quick-login helper
// (see routes/DevLogin.jsx) — it does NOT authenticate anyone by itself.
// DevLogin still submits through AuthContext's real login(), which only
// ever succeeds via a genuine POST /auth/login against the backend.
//
// All seeded accounts share one password (see scripts/setup.sh):
export const SEEDED_ACCOUNT_PASSWORD = "GovSecure@2026";

export const SEEDED_ACCOUNTS = [
  {
    role_label: "Platform Administrator",
    email: "admin.sharma@legadoc.gov.in",
    designation: "Director (Information Systems)",
  },
  {
    role_label: "Investigating Officer (IO)",
    email: "officer.rao@police.gov.in",
    designation: "Inspector of Police (Cyber Cell)",
  },
  {
    role_label: "Duty Officer (Station Intake)",
    email: "duty.verma@police.gov.in",
    designation: "Duty Officer (Station Intake)",
  },
  {
    role_label: "Station House Officer (SHO)",
    email: "sho.singh@police.gov.in",
    designation: "Station House Officer",
  },
  {
    role_label: "Judicial Bench (Magistrate)",
    email: "magistrate.iyer@court.gov.in",
    designation: "Chief Judicial Magistrate",
  },
  {
    role_label: "Public Prosecutor",
    email: "prosecutor.sen@court.gov.in",
    designation: "Senior Public Prosecutor",
  },
  {
    role_label: "Forensic Lab (FSL)",
    email: "fsl.director@fsl.gov.in",
    designation: "Senior Scientific Officer",
  },
  {
    role_label: "Defense Counsel",
    email: "defense.advocate@bar.in",
    designation: "Advocate-on-Record",
  },
  {
    role_label: "NCRB Analyst",
    email: "analyst.ncrb@nic.in",
    designation: "Senior Statistical Officer",
  },
];

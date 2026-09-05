import { apiGet } from "@/lib/api"; import { CaseRow, CaseTable } from "../components/CaseTable";
export default async function Mandates() { return <CaseTable title="Mandate retry queue" rows={await apiGet<CaseRow[]>("/api/dashboard/cases?workflow=MANDATE_RETRY")} />; }

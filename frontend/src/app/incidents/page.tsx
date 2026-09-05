import { apiGet } from "@/lib/api"; import { CaseRow, CaseTable } from "../components/CaseTable";
export default async function Incidents() { return <CaseTable title="Payment degradation incidents" rows={await apiGet<CaseRow[]>("/api/dashboard/cases?workflow=PAYMENT_DEGRADATION")} />; }

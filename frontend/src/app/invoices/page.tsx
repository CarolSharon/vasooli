import { apiGet } from "@/lib/api"; import { CaseRow, CaseTable } from "../components/CaseTable";
export default async function Invoices() { return <CaseTable title="B2B invoice chaser" rows={await apiGet<CaseRow[]>("/api/dashboard/cases?workflow=B2B_RECEIVABLE")} />; }

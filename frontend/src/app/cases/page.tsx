import { apiGet } from "@/lib/api"; import { CaseRow, CaseTable } from "../components/CaseTable";
export default async function Cases() { return <CaseTable title="Recovery queue" rows={await apiGet<CaseRow[]>("/api/dashboard/cases")} />; }

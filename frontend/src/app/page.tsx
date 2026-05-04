import { redirect } from "next/navigation";

// 루트(/) 접속 시 대시보드로 바로 이동
export default function Home() {
  redirect("/dashboard/kr");
}

import { notFound } from "next/navigation";
import AccountAction from "@/components/account-action";

export default async function AccountPage({ params }: { params: Promise<{ action: string }> }) {
  const { action } = await params;
  if (action !== "recovery" && action !== "reset" && action !== "invite") notFound();
  return <AccountAction key={action} kind={action} />;
}

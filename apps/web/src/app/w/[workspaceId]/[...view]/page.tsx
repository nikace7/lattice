import { notFound } from "next/navigation";
import Library from "@/components/library";

export default async function WorkspacePage({
  params,
}: {
  params: Promise<{ workspaceId: string; view: string[] }>;
}) {
  const { workspaceId, view } = await params;
  const route = view.join("/");
  if (
    !["documents", "settings/members"].includes(route) ||
    !/^[0-9a-f-]{36}$/i.test(workspaceId)
  )
    notFound();
  return <Library workspaceId={workspaceId} view={route} />;
}

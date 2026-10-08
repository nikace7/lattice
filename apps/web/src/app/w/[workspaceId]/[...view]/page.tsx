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
    (!["documents", "collections", "search", "ask", "evaluations", "settings/members"].includes(route) && !/^evaluations\/[a-z0-9-]{1,64}$/.test(route) && !/^c\/[0-9a-f-]{36}$/i.test(route) && !/^documents\/[0-9a-f-]{36}(\/passages\/[0-9a-f-]{36})?$/i.test(route)) ||
    !/^[0-9a-f-]{36}$/i.test(workspaceId)
  )
    notFound();
  return <Library workspaceId={workspaceId} view={route} />;
}

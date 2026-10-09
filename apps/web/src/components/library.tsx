"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  api,
  type Collection,
  type Page,
  type Session,
  type Workspace,
} from "@/lib/api";
import { CollectionAccess, Members } from "./workspace-access";
import { Documents } from "./documents";
import { Search } from "./search";
import { Ask } from "./ask";
import { Evaluations } from "./evaluations";
import { CommandMenu } from "./command-menu";
import { Icon } from "./icon";
import {
  ErrorNotice,
  Loading,
  Pagination,
  useAction,
  useResource,
} from "./resource";

function Brand() {
  return (
    <Link href="/" className="wordmark" aria-label="Lattice home">
      <span className="brand-symbol" aria-hidden="true">
        <Icon name="library" />
      </span>{" "}
      lattice
    </Link>
  );
}

export function Authentication({ onSuccess, invitation = false }: { onSuccess: () => void; invitation?: boolean }) {
  const [register, setRegister] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const action = useAction();
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    void action.run(async () => {
      await api<Session>(`/auth/${register ? "register" : "login"}`, "POST", {
        username: values.get("username"),
        password: values.get("password"),
        ...(register ? { email: values.get("email") } : {}),
      });
      onSuccess();
    });
  }
  return (
    <div className="auth-layout">
      <section className="auth-story" aria-label="About Lattice">
        <Brand />
        <div>
          <p className="eyebrow">A shared knowledge workspace</p>
          <h2>
            Answers begin
            <br />with a source.
          </h2>
          <p>
            Bring your team’s documents together. Find the passage you need.
            Keep the evidence within reach.
          </p>
        </div>
        <ol className="auth-workflow"><li><span>01</span><div><strong>Build your library</strong><small>Private collections for your team’s documents.</small></div></li><li><span>02</span><div><strong>Find the right passage</strong><small>Search by words or meaning.</small></div></li><li><span>03</span><div><strong>Read the evidence</strong><small>Open the original source behind a citation.</small></div></li></ol>
      </section>
      <main id="main" tabIndex={-1} className="auth-main">
        <div className="auth-form">
          <p className="eyebrow">Your library awaits</p>
          <h1>{register ? "Create your account" : "Welcome back"}</h1>
          <p className="muted">
            {invitation ? "Use the email address that received your invitation. You can accept it after signing in." : register
              ? "Start a library of your own, or join your team."
              : "Sign in to return to your workspace."}
          </p>
          <form onSubmit={submit}>
            {register && <>
              <label htmlFor="email">Email address</label>
              <input id="email" name="email" type="email" autoComplete="email" required maxLength={254} disabled={action.busy} />
            </>}
            <label htmlFor="username">Username</label>
            <input
              id="username"
              name="username"
              autoComplete="username"
              maxLength={150}
              required
              disabled={action.busy}
            />
            <label htmlFor="password">Password</label>
            <div className="password-field"><input
              id="password"
              name="password"
              type={showPassword ? "text" : "password"}
              autoComplete={register ? "new-password" : "current-password"}
              minLength={register ? 8 : undefined}
              maxLength={128}
              required
              disabled={action.busy}
            /><button type="button" disabled={action.busy} aria-pressed={showPassword} aria-controls="password" onClick={() => setShowPassword(!showPassword)}>{showPassword ? "Hide password" : "Show password"}</button></div>
            {register && (
              <p className="field-note">
                Use at least 8 characters and avoid common passwords.
              </p>
            )}
            <ErrorNotice error={action.error} />
            <button
              className="primary-button full-width"
              disabled={action.busy}
            >
              {action.busy
                ? "Please wait…"
                : register
                  ? "Create account"
                  : "Sign in"}
            </button>
          </form>
          {!register && <p><Link href="/account/recovery">Forgot your password?</Link></p>}
          <p className="switch-auth">
            {register ? "Already have an account?" : "New to Lattice?"}{" "}
            <button
              className="text-button"
              disabled={action.busy}
              onClick={() => setRegister(!register)}
            >
              {register ? "Sign in instead" : "Create an account"}
            </button>
          </p>
          <p className="release-note">
            Early access · Search indexed documents and inspect their sources.
            Ask questions with verified source passages when local generation is configured.
          </p>
        </div>
      </main>
    </div>
  );
}

function SignOut({
  username,
  onSignedOut,
}: {
  username: string;
  onSignedOut: () => void;
}) {
  const action = useAction();
  const router = useRouter();
  return (
    <div className="account-control">
      <span className="username" title={username}>
        {username}
      </span>
      <button
        className="text-button"
        disabled={action.busy}
        onClick={() =>
          void action.run(async () => {
            await api("/auth/logout", "POST");
            onSignedOut();
            router.replace("/");
          })
        }
      >
        Sign out
      </button>
      <ErrorNotice error={action.error} />
    </div>
  );
}

function Lobby({
  user,
  onSignedOut,
}: {
  user: NonNullable<Session["user"]>;
  onSignedOut: () => void;
}) {
  const router = useRouter();
  const [path, setPath] = useState("/workspaces");
  const workspaces = useResource<Page<Workspace>>(path);
  const action = useAction();
  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    void action.run(async () => {
      const workspace = await api<Workspace>("/workspaces", "POST", {
        name: new FormData(form).get("name"),
      });
      router.push(`/w/${workspace.id}/collections`);
    });
  }
  return (
    <div className="lobby">
      <header className="topbar">
        <Brand />
        <SignOut username={user.username} onSignedOut={onSignedOut} />
      </header>
      <main id="main" tabIndex={-1} className="lobby-main">
        <p className="eyebrow">Workspace directory</p>
        <h1>Your workspaces</h1>
        <p className="muted">
          Choose a workspace to open its documents and collections.
        </p>
        <ErrorNotice error={workspaces.error} retry={workspaces.reload} />
        {!workspaces.data && !workspaces.error && <Loading />}
        {workspaces.data && (
          <>
            <div className="workspace-list">
              {workspaces.data.results.map((workspace) => (
                <Link
                  className="workspace-row"
                  href={`/w/${workspace.id}/documents`}
                  key={workspace.id}
                >
                  <span className="workspace-monogram" aria-hidden="true">
                    {workspace.name[0]}
                  </span>
                  <span>
                    <strong>{workspace.name}</strong>
                    <small>{workspace.role.toLowerCase()}</small>
                  </span>
                  <span aria-hidden="true">↗</span>
                </Link>
              ))}
            </div>
            {!workspaces.data.results.length && (
              <p className="empty-caption">
                No workspaces yet. Create your first one below, or ask an owner
                to add your username.
              </p>
            )}
            <Pagination page={workspaces.data} onPage={setPath} />
          </>
        )}
        <section
          className="create-workspace"
          aria-labelledby="create-workspace-title"
        >
          <h2 id="create-workspace-title">Create a workspace</h2>
          <form onSubmit={create}>
            <label htmlFor="workspace-name">Workspace name</label>
            <div className="inline-form">
              <input
                id="workspace-name"
                name="name"
                placeholder="e.g. Studio library"
                maxLength={120}
                required
                disabled={action.busy}
              />
              <button className="primary-button" disabled={action.busy}>
                Create workspace
              </button>
            </div>
            <ErrorNotice error={action.error} />
          </form>
        </section>
      </main>
    </div>
  );
}

function CollectionList({
  workspace,
  onSelect,
}: {
  workspace: Workspace;
  onSelect: (id: string) => void;
}) {
  const base = `/workspaces/${workspace.id}/collections`;
  const [path, setPath] = useState(base);
  const collections = useResource<Page<Collection>>(path);
  const [creating, setCreating] = useState(false);
  const action = useAction();
  const canCreate = ["OWNER", "CURATOR"].includes(workspace.role);
  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    void action.run(async () => {
      const collection = await api<Collection>(base, "POST", {
        title: values.get("title"),
        access: values.get("access") ?? "WORKSPACE",
      });
      form.reset();
      setCreating(false);
      collections.reload();
      onSelect(collection.id);
    });
  }
  return (
    <section aria-labelledby="collection-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Library / Organization</p>
          <h1 id="collection-title">Collections</h1>
        </div>
        {canCreate && (
          <button
            className="primary-button"
            onClick={() => setCreating(!creating)}
            aria-expanded={creating}
          >
            {creating ? "Close form" : "New collection"}
          </button>
        )}
      </div>
      <p className="muted">
        Give related documents a place together. Decide who can read and
        contribute.
      </p>
      {creating && (
        <form onSubmit={create} className="collection-form">
          <label htmlFor="collection-title-input">Collection title</label>
          <input
            id="collection-title-input"
            name="title"
            maxLength={160}
            required
            disabled={action.busy}
          />
          {workspace.role === "OWNER" && (
            <>
              <label htmlFor="collection-access">Who can read it?</label>
              <select
                id="collection-access"
                name="access"
                disabled={action.busy}
              >
                <option value="WORKSPACE">Everyone in this workspace</option>
                <option value="RESTRICTED">
                  Selected people (owners only until granted)
                </option>
              </select>
            </>
          )}
          <ErrorNotice error={action.error} />
          <button className="primary-button" disabled={action.busy}>
            Create collection
          </button>
        </form>
      )}
      <ErrorNotice error={collections.error} retry={collections.reload} />
      {!collections.data && !collections.error && (
        <Loading>Finding your collections…</Loading>
      )}
      {collections.data && (
        <>
          {collections.data.results.length ? (
            <div className="collection-list">
              {collections.data.results.map((collection) => (
                <button
                  className="collection-row"
                  key={collection.id}
                  onClick={() => onSelect(collection.id)}
                >
                  <span className="collection-icon" aria-hidden="true">
                    <Icon name="collections" />
                  </span>
                  <span className="collection-row-title">
                    <strong>{collection.title}</strong>
                    <small>
                      {collection.access === "RESTRICTED"
                        ? "Selected people"
                        : "Workspace collection"}
                    </small>
                  </span>
                  <span className="access-badge">
                    {collection.canWrite ? "Can contribute" : "Read only"}
                  </span>
                  <span aria-hidden="true">↗</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="empty-library">
              <span className="empty-symbol" aria-hidden="true">
                <Icon name="collections" />
              </span>
              <h2>
                {canCreate
                  ? "Start with a collection."
                  : "There’s room for knowledge here."}
              </h2>
              <p>
                {canCreate
                  ? "Policies, project notes, or research. Give your first collection a name."
                  : "Your team’s shared collections will appear here. Ask an owner if you need access."}
              </p>
              {canCreate && !creating && (
                <button onClick={() => setCreating(true)}>
                  Create your first collection
                </button>
              )}
            </div>
          )}
          <Pagination page={collections.data} onPage={setPath} />
        </>
      )}
      <div className="phase-note">
        <span aria-hidden="true">↳</span>
        <p>
          <Link href={`/w/${workspace.id}/${canCreate ? "documents" : "search"}`}>{canCreate ? "Add documents" : "Search your collections"}</Link> and read the source text.
        </p>
      </div>
    </section>
  );
}

function WorkspaceRoom({
  id,
  view,
  user,
  onSignedOut,
}: {
  id: string;
  view: string;
  user: NonNullable<Session["user"]>;
  onSignedOut: () => void;
}) {
  const workspace = useResource<Workspace>(`/workspaces/${id}`);
  const [selected, setSelected] = useState<string>();
  const [listVersion, setListVersion] = useState(0);
  const [drawer, setDrawer] = useState(false);
  const menu = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (drawer) menu.current?.showModal();
    else menu.current?.close();
    function resized() { if (window.innerWidth >= 768) setDrawer(false); }
    window.addEventListener("resize", resized);
    return () => window.removeEventListener("resize", resized);
  }, [drawer]);
  const isMembers = view === "settings/members";
  const isSearch = view === "search";
  const isAsk = view === "ask" || view.startsWith("c/");
  const isDocuments = view === "documents" || view.startsWith("documents/");
  const isEvaluations = view === "evaluations" || view.startsWith("evaluations/");
  const navigation = <nav aria-label="Workspace">
    <Link href={`/w/${id}/documents`} aria-current={isDocuments ? "page" : undefined} onClick={() => setDrawer(false)}><Icon name="documents" /> Documents</Link>
    <Link href={`/w/${id}/collections`} aria-current={!isMembers && !isDocuments && !isSearch && !isAsk && !isEvaluations ? "page" : undefined} onClick={() => setDrawer(false)}><Icon name="collections" /> Collections</Link>
    <Link href={`/w/${id}/search`} aria-current={isSearch ? "page" : undefined} onClick={() => setDrawer(false)}><Icon name="search" /> Search</Link>
    <Link href={`/w/${id}/ask`} aria-current={isAsk ? "page" : undefined} onClick={() => setDrawer(false)}><Icon name="ask" /> Ask</Link>
    {workspace.data?.role === "OWNER" && <>
      <Link href={`/w/${id}/evaluations`} aria-current={isEvaluations ? "page" : undefined} onClick={() => setDrawer(false)}><Icon name="chart" /> Evaluations</Link>
      <Link href={`/w/${id}/settings/members`} aria-current={isMembers ? "page" : undefined} onClick={() => setDrawer(false)}><Icon name="people" /> People & access</Link>
    </>}
  </nav>;
  return (
    <div className="room">
      <header className="topbar">
        <Brand />
        {workspace.data && <CommandMenu workspace={workspace.data} />}
        <button
          className="mobile-menu"
          aria-label="Workspace menu"
          aria-haspopup="dialog"
          aria-expanded={drawer}
          aria-controls="workspace-menu"
          onClick={() => setDrawer(!drawer)}
        >
          <Icon name="menu" />
        </button>
        <SignOut username={user.username} onSignedOut={onSignedOut} />
      </header>
      <dialog ref={menu} id="workspace-menu" className="workspace-menu" aria-label="Workspace menu" onClose={() => setDrawer(false)} onCancel={() => setDrawer(false)}>
        <button onClick={() => setDrawer(false)}>Close menu</button>
        <h2>{workspace.data?.name ?? "Workspace"}</h2>{navigation}
      </dialog>
      <div className="room-grid">
        <aside
          className="rail"
          id="workspace-nav"
        >
          <Link className="back-link" href="/">
            ← All workspaces
          </Link>
          <h2 className="rail-workspace">
            {workspace.data?.name ?? "Workspace"}
          </h2>
          {workspace.data && (
            <span className="role-label">
              {workspace.data.role.toLowerCase()}
            </span>
          )}
          {navigation}
          <div className="rail-footer">
            <Icon name="library" /> Team library<p>Access is managed by your workspace owner.</p>
          </div>
        </aside>
        <main id="main" tabIndex={-1} className={`room-main ${isDocuments || isSearch || isAsk || isEvaluations ? "document-main" : ""}`}>
          <ErrorNotice error={workspace.error} retry={workspace.reload} />
          {!workspace.data && !workspace.error && <Loading />}
          {workspace.data &&
            (isMembers ? (
              <Members workspace={workspace.data} onChange={workspace.reload} />
            ) : isEvaluations ? (
              <Evaluations workspace={workspace.data} reportId={view.split("/")[1]} />
            ) : isDocuments ? (
              <Documents key={view} workspace={workspace.data} documentId={view.split("/")[1]} chunkId={view.split("/")[3]} />
            ) : isSearch ? (
              <Search key={id} workspace={workspace.data} />
            ) : isAsk ? (
              <Ask key={`${id}:${view}`} workspace={workspace.data} conversationId={view.startsWith("c/") ? view.split("/")[1] : undefined} />
            ) : (
              <CollectionList
                key={`${id}:${listVersion}`}
                workspace={workspace.data}
                onSelect={setSelected}
              />
            ))}
        </main>
        {!isMembers && !isDocuments && !isSearch && !isAsk && !isEvaluations && workspace.data && (
          <aside className="inspector" aria-label="Collection details">
            {selected ? (
              <CollectionAccess
                key={selected}
                workspace={workspace.data}
                id={selected}
                onClose={() => setSelected(undefined)}
                onChange={() => setListVersion((n) => n + 1)}
              />
            ) : (
              <>
                <p className="eyebrow">Collection inspector</p>
                <h2>Collection details</h2>
                <p>
                  Select a collection to see its details and who can use it.
                </p>
                <p className="inspector-footnote">
                  Workspace collections are shared with members. Restricted collections have their own access grants.
                </p>
              </>
            )}
          </aside>
        )}
      </div>
    </div>
  );
}

export default function Library({
  workspaceId,
  view = "documents",
}: {
  workspaceId?: string;
  view?: string;
}) {
  const session = useResource<Session>("/auth/session");
  if (session.error)
    return (
      <div className="lobby">
        <header className="topbar">
          <Brand />
        </header>
        <main id="main" className="lobby-main">
          <h1>Your library is waiting.</h1>
          <ErrorNotice error={session.error} retry={session.reload} />
        </main>
      </div>
    );
  if (!session.data)
    return (
      <main id="main" className="lobby-main">
        <Loading />
      </main>
    );
  if (!session.data.user) return <Authentication onSuccess={session.reload} />;
  return workspaceId ? (
    <WorkspaceRoom
      key={workspaceId}
      id={workspaceId}
      view={view}
      user={session.data.user}
      onSignedOut={session.reload}
    />
  ) : (
    <Lobby user={session.data.user} onSignedOut={session.reload} />
  );
}

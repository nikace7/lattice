"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import {
  api,
  type Collection,
  type Page,
  type Session,
  type Workspace,
} from "@/lib/api";
import { CollectionAccess, Members } from "./workspace-access";
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
        ▦
      </span>{" "}
      lattice
      <span className="brand-dot" aria-hidden="true">
        .
      </span>
    </Link>
  );
}

function Authentication({ onSuccess }: { onSuccess: () => void }) {
  const [register, setRegister] = useState(false);
  const action = useAction();
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    void action.run(async () => {
      await api<Session>(`/auth/${register ? "register" : "login"}`, "POST", {
        username: values.get("username"),
        password: values.get("password"),
      });
      onSuccess();
    });
  }
  return (
    <div className="auth-layout">
      <section className="auth-story" aria-label="About Lattice">
        <Brand />
        <div>
          <p className="eyebrow">THE KNOWLEDGE LIBRARY</p>
          <h2>
            Good knowledge.
            <br />A clear source.
          </h2>
          <p>
            A quiet place for your team’s documents, ideas, and the evidence
            behind them.
          </p>
        </div>
        <p className="auth-footnote">
          Your workspace. Your collections. Your people.
        </p>
      </section>
      <main id="main" tabIndex={-1} className="auth-main">
        <div className="auth-form">
          <p className="eyebrow">MAKE ROOM FOR WHAT YOU KNOW</p>
          <h1>{register ? "Create your account" : "Welcome back"}</h1>
          <p className="muted">
            {register
              ? "Start a library of your own, or join your team."
              : "Sign in to return to your workspace."}
          </p>
          <form onSubmit={submit}>
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
            <input
              id="password"
              name="password"
              type="password"
              autoComplete={register ? "new-password" : "current-password"}
              minLength={register ? 8 : undefined}
              maxLength={128}
              required
              disabled={action.busy}
            />
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
            Early access · Accounts and collections are ready. Document upload
            and cited answers are coming next.
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
      router.push(`/w/${workspace.id}/documents`);
    });
  }
  return (
    <div className="lobby">
      <header className="topbar">
        <Brand />
        <SignOut username={user.username} onSignedOut={onSignedOut} />
      </header>
      <main id="main" tabIndex={-1} className="lobby-main">
        <p className="eyebrow">YOUR READING ROOMS</p>
        <h1>Your workspaces</h1>
        <p className="muted">
          Choose a library, or give your next project a home.
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
          <h2 id="create-workspace-title">A new space to think.</h2>
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
          <p className="eyebrow">YOUR KNOWLEDGE, ORGANIZED</p>
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
                    ▤
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
                ▤
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
          <strong>Next, the documents.</strong> Upload, search, and cited
          answers will follow. Your collections and access settings are saved
          now.
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
  const isMembers = view === "settings/members";
  return (
    <div className="room">
      <header className="topbar">
        <Brand />
        <button
          className="mobile-menu"
          aria-expanded={drawer}
          aria-controls="workspace-nav"
          onClick={() => setDrawer(!drawer)}
        >
          Workspace menu
        </button>
        <SignOut username={user.username} onSignedOut={onSignedOut} />
      </header>
      <div className="room-grid">
        <aside
          className={`rail ${drawer ? "rail-open" : ""}`}
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
          <nav aria-label="Workspace">
            <Link
              href={`/w/${id}/documents`}
              aria-current={!isMembers ? "page" : undefined}
              onClick={() => setDrawer(false)}
            >
              <span aria-hidden="true">▤</span> Collections
            </Link>
            {workspace.data?.role === "OWNER" && (
              <Link
                href={`/w/${id}/settings/members`}
                aria-current={isMembers ? "page" : undefined}
                onClick={() => setDrawer(false)}
              >
                <span aria-hidden="true">♧</span> People & access
              </Link>
            )}
          </nav>
          <div className="rail-footer">
            <span className="small-dot" aria-hidden="true" /> Workspace
            foundation<p>Careful reading starts with the right access.</p>
          </div>
        </aside>
        <main id="main" tabIndex={-1} className="room-main">
          <ErrorNotice error={workspace.error} retry={workspace.reload} />
          {!workspace.data && !workspace.error && <Loading />}
          {workspace.data &&
            (isMembers ? (
              <Members workspace={workspace.data} onChange={workspace.reload} />
            ) : (
              <CollectionList
                key={`${id}:${listVersion}`}
                workspace={workspace.data}
                onSelect={setSelected}
              />
            ))}
        </main>
        {!isMembers && workspace.data && (
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
                <p className="eyebrow">A CLOSER LOOK</p>
                <h2>Every source has a place.</h2>
                <div className="source-illustration" aria-hidden="true">
                  <span />
                  <span />
                  <span className="highlight-line" />
                  <span />
                </div>
                <p>
                  Select a collection to see its details and who can use it.
                </p>
                <p className="inspector-footnote">
                  When documents arrive, this is where their evidence will live.
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

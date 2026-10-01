"use client";

import { useState, type FormEvent } from "react";
import {
  api,
  type Collection,
  type Grant,
  type Member,
  type Page,
  type Workspace,
} from "@/lib/api";
import {
  ErrorNotice,
  Loading,
  Pagination,
  useAction,
  useResource,
} from "./resource";

const roles = ["OWNER", "CURATOR", "MEMBER", "VIEWER"] as const;

function RoleOptions() {
  return roles.map((role) => (
    <option value={role} key={role}>
      {role[0] + role.slice(1).toLowerCase()}
    </option>
  ));
}

export function Members({
  workspace,
  onChange,
}: {
  workspace: Workspace;
  onChange: () => void;
}) {
  const [path, setPath] = useState(`/workspaces/${workspace.id}/memberships`);
  const members = useResource<Page<Member>>(path);
  const action = useAction();
  function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    void action.run(async () => {
      await api(`/workspaces/${workspace.id}/memberships`, "POST", {
        username: values.get("username"),
        role: values.get("role"),
      });
      form.reset();
      members.reload();
    });
  }
  if (workspace.role !== "OWNER")
    return (
      <section>
        <h1>People & access</h1>
        <p>Only workspace owners can manage membership.</p>
      </section>
    );
  return (
    <section className="members-section">
      <p className="eyebrow">A SHARED SPACE, CLEAR BOUNDARIES</p>
      <h1>People & access</h1>
      <p className="muted">
        Add someone by their existing Lattice username. Their role sets the most
        they can do.
      </p>
      <form onSubmit={add} className="member-add">
        <div>
          <label htmlFor="member-username">Username</label>
          <input
            id="member-username"
            name="username"
            required
            maxLength={150}
            disabled={action.busy}
          />
        </div>
        <div>
          <label htmlFor="member-role">Role</label>
          <select
            id="member-role"
            name="role"
            defaultValue="MEMBER"
            disabled={action.busy}
          >
            <RoleOptions />
          </select>
        </div>
        <button className="primary-button" disabled={action.busy}>
          Add person
        </button>
        <ErrorNotice error={action.error} />
      </form>
      <ErrorNotice error={members.error} retry={members.reload} />
      {!members.data && !members.error && (
        <Loading>Finding the people in your workspace…</Loading>
      )}
      {members.data && (
        <>
          <div className="member-list">
            {members.data.results.map((member) => (
              <MemberRow
                key={`${member.id}:${member.revision}`}
                member={member}
                onSaved={() => {
                  members.reload();
                  onChange();
                }}
              />
            ))}
          </div>
          <Pagination page={members.data} onPage={setPath} />
        </>
      )}
      <dl className="role-guide">
        <div>
          <dt>Owner</dt>
          <dd>Manages people and access to every collection.</dd>
        </div>
        <div>
          <dt>Curator</dt>
          <dd>Contributes to collections they can write to.</dd>
        </div>
        <div>
          <dt>Member</dt>
          <dd>Reads accessible collections. Question answering comes later.</dd>
        </div>
        <div>
          <dt>Viewer</dt>
          <dd>
            Reads accessible collections without contributing or generating
            answers.
          </dd>
        </div>
      </dl>
    </section>
  );
}

function MemberRow({
  member,
  onSaved,
}: {
  member: Member;
  onSaved: () => void;
}) {
  const action = useAction();
  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    void action.run(async () => {
      await api(`/memberships/${member.id}`, "PATCH", {
        role: values.get("role"),
        active: values.has("active"),
        expectedRevision: member.revision,
      });
      onSaved();
    });
  }
  return (
    <form
      className="member-row"
      onSubmit={save}
      aria-label={`Membership for ${member.username}`}
    >
      <strong>{member.username}</strong>
      <label className="sr-only" htmlFor={`role-${member.id}`}>
        Role for {member.username}
      </label>
      <select
        id={`role-${member.id}`}
        name="role"
        defaultValue={member.role}
        disabled={action.busy}
      >
        <RoleOptions />
      </select>
      <label className="checkbox-label">
        <input
          type="checkbox"
          name="active"
          defaultChecked={member.active}
          disabled={action.busy}
        />{" "}
        Active
      </label>
      <button disabled={action.busy}>Save</button>
      <ErrorNotice error={action.error} />
    </form>
  );
}

export function CollectionAccess({
  workspace,
  id,
  onClose,
  onChange,
}: {
  workspace: Workspace;
  id: string;
  onClose: () => void;
  onChange: () => void;
}) {
  const collection = useResource<Collection>(`/collections/${id}`);
  function saved() {
    collection.reload();
    onChange();
  }
  return (
    <>
      <div className="inspector-heading">
        <p className="eyebrow">COLLECTION DETAILS</p>
        <button onClick={onClose} aria-label="Close collection details">
          ×
        </button>
      </div>
      <ErrorNotice error={collection.error} retry={collection.reload} />
      {!collection.data && !collection.error && <Loading />}
      {collection.data && (
        <>
          <h2 className="collection-detail-title">{collection.data.title}</h2>
          <span className="access-badge">
            {collection.data.access === "RESTRICTED"
              ? "Selected people"
              : "Everyone in this workspace"}
          </span>
          {collection.data.canWrite ? (
            <CollectionForm
              key={collection.data.revision}
              collection={collection.data}
              owner={workspace.role === "OWNER"}
              onSaved={saved}
            />
          ) : (
            <p className="field-note">
              You have read-only access to this collection.
            </p>
          )}
          {workspace.role === "OWNER" &&
            collection.data.access === "RESTRICTED" && (
              <Grants
                key={collection.data.revision}
                collection={collection.data}
                workspace={workspace}
                onSaved={saved}
              />
            )}
        </>
      )}
    </>
  );
}

function CollectionForm({
  collection,
  owner,
  onSaved,
}: {
  collection: Collection;
  owner: boolean;
  onSaved: () => void;
}) {
  const action = useAction();
  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    void action.run(async () => {
      await api(`/collections/${collection.id}`, "PATCH", {
        title: values.get("title"),
        ...(owner ? { access: values.get("access") } : {}),
        expectedRevision: collection.revision,
      });
      onSaved();
    });
  }
  return (
    <form className="inspector-form" onSubmit={save}>
      <label htmlFor="edit-title">Title</label>
      <input
        id="edit-title"
        name="title"
        maxLength={160}
        defaultValue={collection.title}
        required
        disabled={action.busy}
      />
      {owner && (
        <>
          <label htmlFor="edit-access">Who can read it?</label>
          <select
            id="edit-access"
            name="access"
            defaultValue={collection.access}
            disabled={action.busy}
          >
            <option value="WORKSPACE">Everyone in this workspace</option>
            <option value="RESTRICTED">Selected people</option>
          </select>
          <p className="field-note">
            Owners always have access. Selected people need an explicit grant
            below.
          </p>
        </>
      )}
      <ErrorNotice error={action.error} />
      <button disabled={action.busy}>Save details</button>
    </form>
  );
}

function Grants({
  collection,
  workspace,
  onSaved,
}: {
  collection: Collection;
  workspace: Workspace;
  onSaved: () => void;
}) {
  const grants = useResource<Grant[]>(`/collections/${collection.id}/grants`);
  return (
    <section className="grant-section" aria-label="Collection access grants">
      <h3>People with access</h3>
      <ErrorNotice error={grants.error} retry={grants.reload} />
      {!grants.data && !grants.error && <Loading />}
      {grants.data && (
        <GrantForm
          collection={collection}
          workspace={workspace}
          initial={grants.data}
          onSaved={onSaved}
        />
      )}
    </section>
  );
}

function GrantForm({
  collection,
  workspace,
  initial,
  onSaved,
}: {
  collection: Collection;
  workspace: Workspace;
  initial: Grant[];
  onSaved: () => void;
}) {
  const [draft, setDraft] = useState(initial);
  const [path, setPath] = useState(`/workspaces/${workspace.id}/memberships`);
  const members = useResource<Page<Member>>(path);
  const action = useAction();
  function update(member: Member, value: string) {
    setDraft((previous) => [
      ...previous.filter((grant) => grant.membershipId !== member.id),
      ...(value === "none"
        ? []
        : [
            {
              membershipId: member.id,
              canRead: true,
              canWrite: value === "write",
            },
          ]),
    ]);
  }
  return (
    <>
      <ErrorNotice error={members.error} retry={members.reload} />
      {!members.data && !members.error && <Loading />}
      {members.data && (
        <>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void action.run(async () => {
                await api(`/collections/${collection.id}/grants`, "PUT", {
                  expectedRevision: collection.revision,
                  grants: draft,
                });
                onSaved();
              });
            }}
          >
            <p className="field-note">
              A collection grant cannot give someone more capabilities than
              their workspace role.
            </p>
            {members.data.results
              .filter((member) => member.active && member.role !== "OWNER")
              .map((member) => {
                const grant = draft.find(
                  (item) => item.membershipId === member.id,
                );
                return (
                  <div className="grant-row" key={member.id}>
                    <label htmlFor={`grant-${member.id}`}>
                      {member.username}
                      <small>{member.role.toLowerCase()}</small>
                    </label>
                    <select
                      id={`grant-${member.id}`}
                      value={
                        grant?.canRead
                          ? grant.canWrite && member.role === "CURATOR"
                            ? "write"
                            : "read"
                          : "none"
                      }
                      onChange={(event) => update(member, event.target.value)}
                      disabled={action.busy}
                    >
                      <option value="none">No access</option>
                      <option value="read">Can read</option>
                      {member.role === "CURATOR" && (
                        <option value="write">Can contribute</option>
                      )}
                    </select>
                  </div>
                );
              })}
            <ErrorNotice error={action.error} />
            <button className="primary-button" disabled={action.busy}>
              Save access
            </button>
          </form>
          <Pagination page={members.data} onPage={setPath} />
        </>
      )}
    </>
  );
}

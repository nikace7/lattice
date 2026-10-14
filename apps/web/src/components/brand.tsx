import Link from "next/link";
import { Icon } from "./icon";

export function Brand() {
  return (
    <Link href="/" className="wordmark" aria-label="Lattice home">
      <span className="brand-symbol" aria-hidden="true">
        <Icon name="library" />
      </span>{" "}
      lattice
    </Link>
  );
}

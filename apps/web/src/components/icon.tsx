const paths = {
  library: "M4 3v18M9 3v18M14 3v18M18 3l3 18M3 18h12",
  collections: "M3 7h7l2-3h9v16H3z",
  documents: "M5 3h9l5 5v13H5zM14 3v6h5M8 13h8M8 17h6",
  search: "M15 15l6 6M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0",
  ask: "M4 4h16v12H9l-5 5zM8 8h8M8 12h5",
  people: "M15 21v-3a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v3M21 21v-3a4 4 0 0 0-3-4M12 6a3 3 0 1 1-6 0 3 3 0 0 1 6 0M17 3a3 3 0 0 1 0 6",
  chart: "M4 3v18h17M8 16v-4M13 16V6M18 16V9",
  arrow: "M5 12h14M13 6l6 6-6 6",
  plus: "M12 5v14M5 12h14",
  menu: "M4 6h16M4 12h16M4 18h16",
} as const;

export function Icon({ name }: { name: keyof typeof paths }) {
  return <svg className="icon" aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d={paths[name]} /></svg>;
}

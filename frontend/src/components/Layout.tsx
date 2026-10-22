import { NavLink, Outlet } from "react-router-dom";

export function Layout() {
  return (
    <div className="app">
      <header className="app-header">
        <span className="brand">Job Apply</span>
        <nav>
          <NavLink to="/" end>
            Jobs
          </NavLink>
          <NavLink to="/extract">Extract</NavLink>
        </nav>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}

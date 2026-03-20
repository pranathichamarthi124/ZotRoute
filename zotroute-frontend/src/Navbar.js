import React from "react";
import "./Navbar.css";

export default function Navbar({ isPanelOpen }) {
  return (
    <nav
      className="nav"
      style={{
        marginLeft: isPanelOpen ? "350px" : "0px",
        transition: "margin-left 0.3s ease",
      }}
    >
      <div className="nav-proj-name">
        <h1>ZotRoute</h1>
        <p>One-Stop UCI Commute</p>
      </div>
    </nav>
  );
}

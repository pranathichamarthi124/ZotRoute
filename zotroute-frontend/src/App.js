import React, { useState } from "react";
import MapView from "./MapView";
import Navbar from "./Navbar";

function App() {
  const [filter, setFilter] = useState("all");

  return (
    <div className="App">
      <Navbar filter={filter} setFilter={setFilter} />
      <MapView filter={filter} />
    </div>
  );
}

export default App;

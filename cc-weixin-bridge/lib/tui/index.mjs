import React from "react";
import { render } from "ink";
import { App } from "./App.mjs";

export function startTUI({ forceLogin = false } = {}) {
  render(React.createElement(App, { forceLogin }));
}

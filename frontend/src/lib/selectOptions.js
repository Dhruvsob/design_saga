import { Children, Fragment, isValidElement } from "react";

const textOf = (node) => {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isValidElement(node)) return textOf(node.props.children);
  return "";
};

/** Flatten <option>/<optgroup> children (mapped arrays and fragments included). */
export function readOptions(children) {
  const out = [];
  const walk = (nodes, group) => {
    Children.forEach(nodes, (child) => {
      if (!isValidElement(child)) return;
      if (child.type === Fragment) return walk(child.props.children, group);
      if (child.type === "optgroup") return walk(child.props.children, child.props.label);
      if (child.type === "option") {
        const label = textOf(child.props.children).trim();
        out.push({
          value: String(child.props.value ?? label),
          label,
          disabled: Boolean(child.props.disabled),
          group: group || "",
        });
      }
    });
  };
  walk(children);
  return out;
}

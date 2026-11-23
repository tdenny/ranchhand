export default {
  extends: ["stylelint-config-standard"],
  rules: {
    // The stylesheet deliberately keeps short rules on one line.
    "declaration-block-single-line-max-declarations": null,
    // kebab-case, plus BEM-style elements/modifiers (.choices__list--dropdown) for Choices.js.
    "selector-class-pattern": "^[a-z][a-z0-9]*(-[a-z0-9]+)*(__[a-z0-9]+(-[a-z0-9]+)*)?(--[a-z0-9]+(-[a-z0-9]+)*)?$",
  },
};

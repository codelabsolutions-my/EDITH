<!-- Thanks for contributing to EDITH! Please fill this out. -->

## What & why

<!-- What does this PR do, and why? Link any related issue: Closes #123 -->

## Type

- [ ] feat
- [ ] fix
- [ ] docs
- [ ] refactor / chore / test
- [ ] connector

## Checklist

- [ ] My commits are **signed off** (`git commit -s`) per the [DCO](../CONTRIBUTING.md#developer-certificate-of-origin-dco)
- [ ] `make lint test` passes locally
- [ ] I followed [Conventional Commits](https://www.conventionalcommits.org/)
- [ ] I added/updated tests where it makes sense
- [ ] I updated docs where it makes sense

## For connectors only

- [ ] Requests **minimal**, incremental OAuth scopes
- [ ] Every external/irreversible tool is classed `confirm` (not `auto`)
- [ ] No logging/transmission of tokens, secrets, or PII
- [ ] Uses an official, ToS-compliant API
- [ ] `make test-connectors` passes

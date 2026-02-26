# TO-DO:

[ ]- remove "proposal-to-metaprompt" from root ~/.claude
[x] - rename to "proposal-evolution" here
[ ] - create whatever manifests are necessary to be able to load it like taches' prompts
[ ] - start by finding the latest evolution of the prompt
    [ ] - first look in prompts/proposal - can have multiple proposal evolutions in there; pick the latest (highest number)
    [ ] - only if nothing found there should it look in prompts/
    [ ] - start with 3-digit numbering; if none found then fall back to 2-digit, then 1-digit, then 0-digit
    [ ] - if 0-2 digits then rename to 3-digit.
    [ ] - if "999 - " already exists then make that the latest in the 3-digit naming convention and use that, *unless* specifically told to use the latest manually-created revision instead
[ ] - final output is prefixed with "999 - " (i.e. final revision) - this can be overwritten entirely each time this runs.
    [ ] - *could* make the latest numeric revision, unless specifically told otherwise.
.


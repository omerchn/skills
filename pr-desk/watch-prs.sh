#!/bin/bash
# Polls GitHub every 2 minutes and emits one line per actionable PR:
#   approve: <url>  every thread I started on someone else's PR is resolved or replied to (and changed since last emit)
#   fix: <url>      my own PR has a new unresolved thread whose last comment isn't mine
#   conflict: <url> my own PR conflicts with its base (once per head commit)
#   watcher error: ...
set -o pipefail
DIR="$(cd "$(dirname "$0")" && pwd)/state"
mkdir -p "$DIR"
ME=$(gh api user --jq .login) || { echo "watcher error: gh auth failed"; exit 1; }
for f in approve fix conflict; do [ -f "$DIR/$f.json" ] || echo '{}' > "$DIR/$f.json"; done

query() {
  gh api graphql -f q="$1" -f query='
query($q:String!){ search(query:$q, type:ISSUE, first:50){ nodes{ ... on PullRequest{
  url headRefOid mergeable
  latestOpinionatedReviews(first:20){ nodes{ author{login} state } }
  reviewThreads(first:50){ nodes{ id isResolved isOutdated
    first: comments(first:1){ nodes{ author{login} } }
    rest: comments(last:20){ nodes{ author{login} } } } }
}}}}' 2>/dev/null
}

emit() { # $1 = kind, $2 = current state json
  jq -r -n --arg k "$1" --argjson p "$(cat "$DIR/$1.json")" --argjson c "$2" '
    $c | to_entries[]
    | if $k == "approve"
      then select($p[.key] != .value and (.value | startswith("A|")))
      elif $k == "conflict" then select($p[.key] != .value)
      else select(((.value | split(",")) - ($p[.key] // "" | split(","))) - [""] | length > 0)
      end
    | "\($k): \(.key)"'
  echo "$2" > "$DIR/$1.json"
}

while true; do
  approve=$(query 'org:Orchid-Security is:pr is:open reviewed-by:@me -author:@me' | jq -c --arg me "$ME" '
    [.data.search.nodes[]
     | select(any(.latestOpinionatedReviews.nodes[]; .author.login == $me and .state == "APPROVED") | not)
     | {url, head: .headRefOid, mine: [.reviewThreads.nodes[] | select(.first.nodes[0].author.login == $me)]}
     | select(.mine | length > 0)
     | {key: .url, value: "\(if (.mine | all(.isResolved or any(.rest.nodes[]; .author.login != $me))) then "A" else "P" end)|\(.mine | map(select(.isResolved)) | length)/\(.mine | map(.rest.nodes[] | select(.author.login != $me)) | length)/\(.head)"}
    ] | from_entries') && emit approve "$approve" || echo "watcher error: approve query failed"

  mine=$(query 'org:Orchid-Security is:pr is:open author:@me') || { echo "watcher error: my-PRs query failed"; sleep 120; continue; }

  conflict=$(jq -c '[.data.search.nodes[] | select(.mergeable == "CONFLICTING") | {key: .url, value: .headRefOid}] | from_entries' <<< "$mine") \
    && emit conflict "$conflict" || echo "watcher error: conflict parse failed"

  fix=$(jq -c --arg me "$ME" <<< "$mine" '
    [.data.search.nodes[]
     | {key: .url, value: ([.reviewThreads.nodes[]
         | select((.isResolved | not) and (.rest.nodes[-1].author.login != $me)) | .id]
         | sort | join(","))}
    ] | from_entries') && emit fix "$fix" || echo "watcher error: fix parse failed"

  sleep 120
done

# Bogged

Bogged is a framework for dealing with Minecraft mapping triplets. A few things stemmed out of this:

- a reasonably fast bulk Mojmap downloader ([src](scripts/download-mojmap))
- a custom binary format for compact and efficient Minecraft mapping conversion ([docs](docs/format.md))
- an easy to use tool for comparing and converting Minecraft mappings ([try](https://qikpl4.github.io/bogged/))

## Full pipeline

Firstly, you'd want to download Mojmap:

```
mkdir -p inputs/mojmap
python scripts/download-mojmap/main.py -i scripts/download-mojmap/golden.txt inputs/mojmap
```

Then you would clone Yarn and Intermediary:

```
git clone https://github.com/FabricMC/yarn.git inputs/yarn
git clone https://github.com/FabricMC/intermediary.git inputs/intermediary
```

Then you can assemble the custom binary data, straight into the web folder (as of writing, totalling only about 70 MB for 12 versions!):

```
python scripts/builder/main.py --yarn-repo inputs/yarn --intermediary-repo inputs/intermediary --mojmap-dir inputs/mojmap --output www/public/data
```

You can then build the web tool:

```
cd www
npm install
npm run build
```

Lastly, you can test the CLI.

```
python cli/main.py --base-url file://$(pwd)/www/public/data --side yarn --version 1.21.11 maintainPrecision
```

## Out of scope

Notably, something out of scope for this project is storing obfuscated names. These can already be obtained trivially through Intermediary, and writing a separate tool to convert between obfuscated and Intermediary is a better choice.

Two tools with a nice interface is still better than manually dealing with multiple text files.

## Why not Loom's migrateMappings?

migrateMappings is designed to migrate an entire codebase at once. Bogged serves a different purpose: quick, ad-hoc and efficient lookup.

There are workloads where Bogged would make more sense, such as checking one or two mappings during an audit or to prove a point. migrateMappings just isn't built for that.

## Experimental: full data

In case the curated versions built by GitHub every push don't suit your needs, an experimental and best-effort bucket can be used containing the data for every possible version.

They are hosted using slower technology and can break at any time.

If you want to use it, set your base URL to this:

```
https://huggingface.co/buckets/qikp/bogged-all-mojmap/resolve
```

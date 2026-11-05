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

Lastly, you can build the web tool:

```
cd www
npm install
npm run build
```

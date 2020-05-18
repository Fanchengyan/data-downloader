import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="data-downloader",
    version="0.0.4",
    author="fanchegyan",
    author_email="fanchy14@lzu.edu.cn",
    description="Make downloading scientific data much easier",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Fanchengyan/data-downloader",
    packages=setuptools.find_packages(),
    install_requires=[
        'requests',
        'aiohttp',
        'tqdm',
        'setuptools'
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)

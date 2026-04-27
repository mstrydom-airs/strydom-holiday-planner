@ECHO OFF
REM Minimal Sphinx build script for Windows.
REM Use ".\make html" during development and ".\make strict" before committing.

pushd %~dp0

set SPHINXBUILD=sphinx-build
set SOURCEDIR=.
set BUILDDIR=_build

if "%1" == "" goto help
if "%1" == "html"   goto html
if "%1" == "strict" goto strict
if "%1" == "clean"  goto clean

:help
%SPHINXBUILD% -M help %SOURCEDIR% %BUILDDIR%
goto end

:html
%SPHINXBUILD% -b html %SOURCEDIR% %BUILDDIR%\html
goto end

:strict
%SPHINXBUILD% -W -b html %SOURCEDIR% %BUILDDIR%\html
goto end

:clean
if exist %BUILDDIR% rmdir /S /Q %BUILDDIR%
goto end

:end
popd

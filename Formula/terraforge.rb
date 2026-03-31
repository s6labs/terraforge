# Homebrew formula for TerraForge — AI-Powered Coder Workspace Template Generator
# Tap:  brew tap s6labs/terraforge
# Install: brew install s6labs/terraforge/terraforge
#
# To update checksums after a new release, run:
#   brew bump-formula-pr --tag vX.Y.Z --revision <commit-sha> terraforge
#
class Terraforge < Formula
  desc "AI-Powered Coder Workspace Template Generator"
  homepage "https://github.com/s6labs/terraforge"
  license "MIT"
  version "1.5.1"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/s6labs/terraforge/releases/download/v#{version}/terraforge-macos-arm64"
      sha256 "03b225f55dc700b8e29c0f4c902b08063a6128048fb392f9c52fd5f2190effcc"

      def install
        bin.install "terraforge-macos-arm64" => "terraforge"
      end
    end
  end

  on_linux do
    if Hardware::CPU.arm?
      url "https://github.com/s6labs/terraforge/releases/download/v#{version}/terraforge-linux-arm64"
      sha256 "REPLACE_WITH_SHA256_LINUX_ARM64"

      def install
        bin.install "terraforge-linux-arm64" => "terraforge"
      end
    else
      url "https://github.com/s6labs/terraforge/releases/download/v#{version}/terraforge-linux-amd64"
      sha256 "00f55b86a8b8a38d5ba11509eeb39fee5a059bbb815143fee0a7a47fd57d3fac"

      def install
        bin.install "terraforge-linux-amd64" => "terraforge"
      end
    end
  end

  test do
    assert_match "terraforge", shell_output("#{bin}/terraforge --help 2>&1", 0)
  end
end

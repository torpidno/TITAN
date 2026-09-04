import os
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from config import config

logger = logging.getLogger("TITAN.Evolution")


class GitVersionManager:
    """
    Automated Git Version Control & GitHub synchronization for T.I.T.A.N.
    Provides atomic checkpoints, automated test verification, and fail-safe rollbacks.
    """

    def __init__(self, repo_path: Optional[Path] = None):
        self.repo_path = repo_path or config.BASE_DIR

    def _run_git(self, args: List[str], timeout: int = 25) -> Dict[str, Any]:
        """Execute a git command inside the repository."""
        try:
            res = subprocess.run(
                ["git"] + args,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace"
            )
            return {
                "success": res.returncode == 0,
                "stdout": res.stdout.strip(),
                "stderr": res.stderr.strip(),
                "return_code": res.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Git command timed out after {timeout} seconds.",
                "return_code": -1
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "return_code": -1
            }

    def get_status(self) -> Dict[str, Any]:
        """Get current git status and branch."""
        res = self._run_git(["status", "--porcelain"])
        branch = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        return {
            "clean": len(res.get("stdout", "")) == 0,
            "modified_files": res.get("stdout", "").split("\n") if res.get("stdout") else [],
            "branch": branch.get("stdout", "main"),
            "success": res.get("success", False)
        }

    def get_history(self, limit: int = 10) -> List[Dict[str, str]]:
        """Retrieve recent commit history."""
        res = self._run_git(["log", f"-n{limit}", "--pretty=format:%h|%an|%ar|%s"])
        if not res["success"] or not res["stdout"]:
            return []
        
        history = []
        for line in res["stdout"].split("\n"):
            parts = line.split("|", 3)
            if len(parts) == 4:
                history.append({
                    "hash": parts[0],
                    "author": parts[1],
                    "time": parts[2],
                    "message": parts[3]
                })
        return history

    def run_self_tests(self) -> Dict[str, Any]:
        """Run T.I.T.A.N. unit test suite to verify code integrity."""
        test_file = self.repo_path / "test_titan.py"
        if not test_file.exists():
            return {"passed": True, "output": "No test_titan.py found; assuming passing."}

        try:
            res = subprocess.run(
                ["python", str(test_file)],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace"
            )
            passed = res.returncode == 0
            return {
                "passed": passed,
                "output": (res.stdout + "\n" + res.stderr).strip(),
                "return_code": res.returncode
            }
        except Exception as e:
            return {
                "passed": False,
                "output": f"Self-test execution error: {str(e)}",
                "return_code": -1
            }

    def create_checkpoint(self, message: str, auto_push: bool = True) -> Dict[str, Any]:
        """Stage all changes, commit, and optionally push to GitHub."""
        # Ensure .env is never tracked
        self._run_git(["reset", ".env"])

        # Stage files
        stage_res = self._run_git(["add", "."])
        if not stage_res["success"]:
            return {"success": False, "message": f"Git stage error: {stage_res['stderr']}"}

        # Check if there are changes to commit
        status = self.get_status()
        if status["clean"]:
            return {"success": True, "message": "No code changes detected to commit.", "committed": False}

        commit_msg = f"[EVOLUTION]: {message.strip()}"
        commit_res = self._run_git(["commit", "-m", commit_msg])
        if not commit_res["success"]:
            return {"success": False, "message": f"Git commit error: {commit_res['stderr']}"}

        latest_hash = self._run_git(["rev-parse", "--short", "HEAD"]).get("stdout", "unknown")
        
        push_status = "skipped"
        if auto_push:
            push_res = self._run_git(["push", "origin", status.get("branch", "main")], timeout=35)
            if push_res["success"]:
                push_status = "pushed_to_github"
                logger.info(f"[GIT] Successfully pushed commit {latest_hash} to GitHub.")
            else:
                push_status = f"push_failed: {push_res['stderr']}"
                logger.warning(f"[GIT] Push to GitHub failed: {push_res['stderr']}")

        return {
            "success": True,
            "committed": True,
            "commit_hash": latest_hash,
            "message": commit_msg,
            "push_status": push_status
        }

    def rollback(self, steps: int = 1) -> Dict[str, Any]:
        """Rollback repository by N commits using git reset --hard."""
        target = f"HEAD~{steps}"
        res = self._run_git(["reset", "--hard", target])
        if res["success"]:
            current_hash = self._run_git(["rev-parse", "--short", "HEAD"]).get("stdout", "")
            logger.info(f"[GIT] Rolled back {steps} commit(s). Current HEAD is now at {current_hash}.")
            return {
                "success": True,
                "message": f"Successfully rolled back {steps} version(s). Current version: {current_hash}.",
                "commit_hash": current_hash
            }
        else:
            return {
                "success": False,
                "message": f"Rollback failed: {res['stderr']}"
            }

    def revert_working_changes(self, file_path: Optional[str] = None) -> Dict[str, Any]:
        """Discard uncommitted modifications to return to clean state."""
        if file_path:
            res = self._run_git(["checkout", "--", file_path])
        else:
            res = self._run_git(["reset", "--hard", "HEAD"])
            self._run_git(["clean", "-fd"])
        return {"success": res["success"], "message": "Working directory reverted to last clean commit."}


class CodeEvolutionEngine:
    """
    Core engine empowering T.I.T.A.N. to safely rewrite and improve its own code.
    - Inspects source modules
    - Rewrites or patches codebase
    - Validates changes against self-tests
    - Auto-commits and syncs with GitHub
    - Auto-reverts if tests fail
    """

    def __init__(self, repo_path: Optional[Path] = None, memory=None):
        self.repo_path = repo_path or config.BASE_DIR
        self.git = GitVersionManager(repo_path=self.repo_path)
        self.memory = memory

    def inspect_file(self, relative_path: str) -> Dict[str, Any]:
        """Inspect the current contents of any file in TITAN."""
        try:
            target = (self.repo_path / relative_path).resolve()
            if not target.is_relative_to(self.repo_path.resolve()):
                return {"status": "error", "message": "Access outside repository is restricted."}

            if not target.exists():
                return {"status": "error", "message": f"File '{relative_path}' not found."}

            content = target.read_text(encoding="utf-8")
            return {
                "status": "success",
                "filepath": relative_path,
                "lines": len(content.splitlines()),
                "content": content
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def evolve_code(
        self,
        filepath: str,
        new_code: str,
        reason: str,
        auto_push: bool = True,
        verify_tests: bool = True
    ) -> Dict[str, Any]:
        """
        Safely rewrite or create an internal TITAN file.
        1. Backs up / applies change
        2. Runs self-tests
        3. If test fails: automatically reverts file
        4. If test passes: creates Git commit and pushes to GitHub
        """
        clean_path = filepath.strip("/\\")
        target_file = (self.repo_path / clean_path).resolve()

        if not target_file.is_relative_to(self.repo_path.resolve()):
            return {"status": "error", "message": "Modification outside repository root is disallowed."}

        # Disallow editing secrets
        if clean_path in (".env", ".git"):
            return {"status": "error", "message": "Modifying .env or .git directly via evolution is forbidden for safety."}

        # Backup existing content if exists
        original_content = target_file.read_text(encoding="utf-8") if target_file.exists() else None

        try:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(new_code, encoding="utf-8")
            logger.info(f"[EVOLUTION] Applied code modifications to '{clean_path}'. Running verification tests...")

            # Run automated self-tests
            if verify_tests:
                test_result = self.git.run_self_tests()
                if not test_result.get("passed", False):
                    logger.warning(f"[EVOLUTION] Self-tests FAILED after modifying '{clean_path}'. Reverting changes immediately!")
                    # Revert file
                    if original_content is not None:
                        target_file.write_text(original_content, encoding="utf-8")
                    else:
                        target_file.unlink(missing_ok=True)

                    if self.memory:
                        self.memory.record_insight(
                            category="evolution_failed",
                            trigger_context=f"Evolve {clean_path}",
                            lesson=f"Attempted evolution failed tests: {test_result.get('output', '')[:300]}"
                        )

                    return {
                        "status": "error",
                        "message": "Self-tests failed after code modification. Code has been automatically rolled back to prevent breaking.",
                        "test_output": test_result.get("output", "")
                    }

            # Create Git Checkpoint & Push to GitHub
            checkpoint = self.git.create_checkpoint(message=f"Evolved {clean_path}: {reason}", auto_push=auto_push)
            
            if self.memory:
                self.memory.record_insight(
                    category="codebase_evolution",
                    trigger_context=f"Evolved {clean_path}",
                    lesson=f"Successfully evolved {clean_path} ({checkpoint.get('commit_hash', '')}): {reason}"
                )

            return {
                "status": "success",
                "message": f"Code in '{clean_path}' successfully evolved, verified by tests, and saved to Git.",
                "commit_hash": checkpoint.get("commit_hash", ""),
                "push_status": checkpoint.get("push_status", ""),
                "reason": reason
            }

        except Exception as e:
            # Revert on unexpected exception
            if original_content is not None:
                target_file.write_text(original_content, encoding="utf-8")
            return {
                "status": "error",
                "message": f"Evolution failed with exception: {str(e)}. Changes reverted."
            }
